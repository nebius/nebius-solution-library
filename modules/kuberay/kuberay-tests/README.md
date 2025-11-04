# Quick tests for kuberay

## Files/Directories

* `example.env`  -- example settings for a `.env` file required for training test
* `pyproject.toml` -- defines the requirements for the run environment
* `ray-infiniband/` -- Contains a simple docker file that includes infiniband userland libraries
* `ray_scale.py` -- script to force auto-scaling and test that it works
* `ray_all_reduce.py` --  performs a simple test/benchmark of the infiniband
* `ray_train.py` -- performs distributed training on a simple model

Scripts can be submitted by port forwarding the kuberay cluster head:

```bash
kubectl -n ray-cluster port-forward services/ray-cluster-kuberay-head-svc 8265:8265
```

And then submitting jobs using (you'll need to have ray installed locally):

```bash
RAY_ADDRESS=http://localhost:8265 ray job submit --working-dir . --runtime-env-json='{"py_executable": "uv run"}' -- uv run script.py`
```
