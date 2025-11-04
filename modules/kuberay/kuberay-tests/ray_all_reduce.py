import ray

# from cupy.cuda import nccl
import time
import statistics
import uuid
import ray.util.collective as col

DTYPE_BYTES = 4
NUM_TRIALS = 5
DTYPE_STR = "float"
REDOP = "sum"
ROOT = -1
MB = 2**20
GB = 2**30

# Use same byte sizes as shown in your NCCL example (256MB → 8GB)
TENSOR_SIZES_BYTES = [
    512 * MB,
    1 * GB,
    2 * GB,
    4 * GB,
    8 * GB,
    # 16 * GB,
    # 32 * GB,
]


ray.init(address="auto")


@ray.remote(num_gpus=1)
class Worker:
    def __init__(self, world_size, rank, jobid):  # , uid):
        self.world_size = world_size
        self.rank = rank
        self.jobid = jobid

    def setup_collective(self):
        # Initialize the collective communication group.
        # 'nccl' is the high-performance backend for GPU communication.
        col.init_collective_group(
            world_size=self.world_size,
            rank=self.rank,
            backend="nccl",
            group_name="default",  # self.jobid,
        )
        print(f"Rank {self.rank} initialized.")
        col.barrier()  # synchronize(0)
        return True

    def run_allreduce(self, n_bytes):
        import cupy
        from cupy.cuda import Device

        DTYPE = cupy.float32

        count = n_bytes // DTYPE_BYTES
        with Device(0):
            x = cupy.ones((count,), dtype=DTYPE) + self.rank

        col.barrier()  # synchronize(0)
        # Warm-up
        col.allreduce(x, "default")  # self.jobid)
        Device(0).synchronize()
        # print(x[:10])

        col.barrier()  # synchronize(0)
        # Timed run
        start = time.perf_counter()
        col.allreduce(x, "default")  # self.jobid)
        Device(0).synchronize()
        end = time.perf_counter()

        # print(x[:10], Device(0))
        return end - start


def main():
    print("Starting up...")
    world_size = 6  # int(ray.cluster_resources().get("GPU", 1))
    jobid = str(uuid.uuid4())
    workers = [Worker.remote(world_size, rank, jobid) for rank in range(world_size)]
    setup = ray.get([w.setup_collective.remote() for w in workers])
    print(setup)

    print(f"# Number of GPUs : {world_size}")
    print("#                                                              out-of-place")
    print(
        "#       size         count      type   redop    root     time   algbw   busbw #wrong"
    )
    print(
        "#        (B)    (elements)                               (us)  (GB/s)  (GB/s)"
    )

    total_busbw = 0.0
    for size_bytes in TENSOR_SIZES_BYTES:
        count = size_bytes // DTYPE_BYTES
        durations = []

        for _ in range(NUM_TRIALS):
            times = ray.get([w.run_allreduce.remote(size_bytes) for w in workers])
            durations.append(max(times))  # synchronized AllReduce timing

        avg_time_s = statistics.mean(durations)
        avg_time_us = avg_time_s * 1e6
        algbw = (size_bytes * 2) / avg_time_s / GB  # GB/s
        busbw = algbw * (world_size - 1) / world_size
        total_busbw += busbw
        wrong = 0
        print(
            f"{size_bytes:12d} {count:12d} {DTYPE_STR:>10} {REDOP:>8} {ROOT:8d} "
            f"{avg_time_us:8.1f} {algbw:7.2f} {busbw:7.2f} {wrong:6d}"
        )

    avg_busbw = total_busbw / len(durations)

    print(f"# Avg bus bandwidth    : {avg_busbw:.3f}")


if __name__ == "__main__":
    main()
