import ray
import os
import time

# Make sure to use the RAY_HEAD_SERVICE env variable which is already set by the driver job pod.
address = os.environ["RAY_HEAD_SERVICE"]
ray.init(address=f"ray://{address}")

USE_GPU = os.getenv("USE_GPU", "false").lower() == "true"

if USE_GPU:
    @ray.remote(num_gpus=1)
    def compute_task(x):
        import torch
        print(f"GPU available? {torch.cuda.is_available()}")
        return x * x
else:
    @ray.remote
    def compute_task(x):
        print(f"Running on CPU: {x}")
        time.sleep(1)
        return x + 1

print("Submitting tasks...")
tasks = [compute_task.remote(i) for i in range(5)]
results = ray.get(tasks)
print("All done! Results:", results)
