# 🍕 GPU Slicing Examples
## Why slice a GPU?
Sometimes you'll encounter scenarios where one GPU has way too much memory or cores for a single workload.
Nowadays GPUs have a large amount of memory and cores available, but there are still countless use cases like small LLMs that don't require as much memory as say a B200.

To address this, NVIDIA offers 3 ways to slice a GPU to make many smaller GPUs out of one physical GPU.

## How can a GPU be sliced?
* Multi-Instance GPU (MIG)
  * As close as you can get to physically separating a GPU into multiple logical GPUs
  * Increases fault isolation by giving each logical GPU its own physical cores and memory
* Time Slicing
  * Allows definition of replicas of GPUs that can be distributed to pods
  * No hardware isolation
* Multi-Process Service (MPS)
  * Most performant option
  * Teams that need the highest performance overall should use this
  * Complicated setup process
