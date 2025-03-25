import torch
import torch.nn as nn
import torch.optim as optim
import torch.utils.data as data
import argparse
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split

# Argument parser for device selection
parser = argparse.ArgumentParser(description="Train a neural network on the Iris dataset with optional hardware acceleration.")
parser.add_argument("--device", type=str, choices=["cpu", "cuda", "mps"], default="cpu",
                    help="Select device: 'cpu', 'cuda', or 'mps' (default: 'cpu')")
args = parser.parse_args()

# Determine device based on user input and availability
if args.device == "cuda" and torch.cuda.is_available():
    device = torch.device("cuda")
elif args.device == "mps" and torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print(f"Using device: {device}")

# Load and preprocess the dataset
print("Loading Iris dataset...")
iris = load_iris()
X = iris.data  # Features
y = iris.target  # Labels
print("Dataset loaded successfully.")

# Convert labels to tensor for PyTorch compatibility
y = torch.tensor(y, dtype=torch.long)
X = torch.tensor(X, dtype=torch.float32)

# Split data into training and testing sets
print("Splitting data into train and test sets...")
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
print(f"Training samples: {len(X_train)}, Testing samples: {len(X_test)}")

# Move data to device
X_train, X_test, y_train, y_test = X_train.to(device), X_test.to(device), y_train.to(device), y_test.to(device)

# Create DataLoader to handle batches
batch_size = 32
train_dataset = data.TensorDataset(X_train, y_train)
test_dataset = data.TensorDataset(X_test, y_test)
train_loader = data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
test_loader = data.DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

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
        x = torch.maximum(x, torch.tensor(0.0, device=device))  # Apply ReLU activation: max(0, x')
        x = x @ self.W2 + self.b2  # Apply second linear transformation: y = x'W2 + b2
        return x

# Model parameters
input_size = 4  # Number of features in the Iris dataset
hidden_size = 10  # Number of hidden neurons
output_size = 3  # Number of output classes (setosa, versicolor, virginica)

# Instantiate the model, define loss function and optimizer
print("Initializing neural network model...")
model = SimpleNN(input_size, hidden_size, output_size).to(device)
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.01)

# Training loop
num_epochs = 40
print("Starting training...")
for epoch in range(num_epochs):
    model.train()
    total_loss = 0
    for batch in train_loader:
        inputs, targets = batch
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    print(f"Epoch [{epoch+1}/{num_epochs}], Loss: {total_loss/len(train_loader):.4f}")

# Evaluation
model.eval()
correct = 0
total = 0
with torch.no_grad():
    for batch in test_loader:
        inputs, targets = batch
        outputs = model(inputs)
        _, predicted = torch.max(outputs, 1)
        correct += (predicted == targets).sum().item()
        total += targets.size(0)

accuracy = 100 * correct / total
print(f"Test Accuracy: {accuracy:.2f}%")
