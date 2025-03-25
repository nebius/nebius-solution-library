import argparse
import os

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
import torch.nn as nn
import torch.optim as optim
import torch.utils.data as data
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data.distributed import DistributedSampler


# Initialize distributed process group
def setup_distributed():
    # Initialize the process group
    dist.init_process_group(backend="nccl")
    
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    torch.cuda.set_device(local_rank)
    
    # Get world size and rank
    world_size = dist.get_world_size()
    rank = dist.get_rank()
    return world_size, rank
    
local_rank = int(os.environ.get("LOCAL_RANK", 0))
device = torch.device(f"cuda:{local_rank}")


# Set up distributed training
world_size, rank = setup_distributed()
print(f"Rank {rank}/{world_size} using device: {device}")

# Load and preprocess the dataset
if rank == 0:
    print("Loading Iris dataset...")
iris = load_iris()
X = iris.data  # Features
y = iris.target  # Labels
if rank == 0:
    print("Dataset loaded successfully.")

# Convert labels to tensor for PyTorch compatibility
y = torch.tensor(y, dtype=torch.long)
X = torch.tensor(X, dtype=torch.float32)

# Split data into training and testing sets
if rank == 0:
    print("Splitting data into train and test sets...")
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
if rank == 0:
    print(f"Training samples: {len(X_train)}, Testing samples: {len(X_test)}")

# Create distributed samplers and DataLoaders
batch_size = 32
train_dataset = data.TensorDataset(X_train, y_train)
test_dataset = data.TensorDataset(X_test, y_test)

# Use DistributedSampler for training data
train_sampler = DistributedSampler(
    train_dataset,
    num_replicas=world_size,
    rank=rank,
    shuffle=True
)

# Create DataLoaders with distributed sampler
train_loader = data.DataLoader(
    train_dataset,
    batch_size=batch_size,
    sampler=train_sampler,
    num_workers=2,
    pin_memory=True
)

# Test loader doesn't need to be distributed
test_loader = data.DataLoader(
    test_dataset, 
    batch_size=batch_size,
    shuffle=False,
    num_workers=2,
    pin_memory=True
)

# Define a simple neural network
class SimpleNN(nn.Module):
    def __init__(self, input_size, hidden_size, output_size):
        super(SimpleNN, self).__init__()
        # Initialize weights and biases manually
        self.W1 = nn.Parameter(torch.randn(input_size, hidden_size) * 0.01)  # First layer weights
        self.b1 = nn.Parameter(torch.zeros(hidden_size))  # First layer biases
        self.W2 = nn.Parameter(torch.randn(hidden_size, output_size) * 0.01)  # Second layer weights
        self.b2 = nn.Parameter(torch.zeros(output_size))  # Second layer biases
    
    def forward(self, x):
        x = x @ self.W1 + self.b1  # Apply first linear transformation: x' = XW1 + b1
        x = torch.maximum(x, torch.tensor(0.0, device=x.device))  # Apply ReLU activation: max(0, x')
        x = x @ self.W2 + self.b2  # Apply second linear transformation: y = x'W2 + b2
        return x

# Model parameters
input_size = 4  # Number of features in the Iris dataset
hidden_size = 10  # Number of hidden neurons
output_size = 3  # Number of output classes (setosa, versicolor, virginica)

# Instantiate the model, define loss function and optimizer
if rank == 0:
    print("Initializing neural network model...")

# Move model to device before wrapping with DDP
model = SimpleNN(input_size, hidden_size, output_size)
# Ensure model parameters are on the correct device
model = model.to(device)

# Wrap model with DDP after moving to device
model = DDP(model, device_ids=[local_rank])

criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.01)

# Training loop
num_epochs = 4000
if rank == 0:
    print("Starting training...")
for epoch in range(num_epochs):
    # Set epoch for sampler
    train_sampler.set_epoch(epoch)
    
    model.train()
    total_loss = 0
    for batch in train_loader:
        inputs, targets = batch
        inputs, targets = inputs.to(device), targets.to(device)
        
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    
    # All-reduce the loss across processes
    avg_loss = total_loss / len(train_loader)
    tensor_loss = torch.tensor(avg_loss).to(device)
    dist.all_reduce(tensor_loss, op=dist.ReduceOp.SUM)
    tensor_loss = tensor_loss / world_size
    
    if rank == 0:
        print(f"Epoch [{epoch+1}/{num_epochs}], Loss: {tensor_loss.item():.4f}")

# Evaluation (only on rank 0 for simplicity)
if rank == 0:
    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for batch in test_loader:
            inputs, targets = batch
            inputs, targets = inputs.to(device), targets.to(device)
            outputs = model(inputs)
            _, predicted = torch.max(outputs, 1)
            correct += (predicted == targets).sum().item()
            total += targets.size(0)

    accuracy = 100 * correct / total
    print(f"Test Accuracy: {accuracy:.2f}%")

# Clean up distributed process group
dist.destroy_process_group()