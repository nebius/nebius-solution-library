# Quick Checks

These checks are intentionally minimal. Use them when you want to verify quota, subnet selection, CLI auth, logs, public endpoint networking, and token authentication before running the real examples.

## GPU Job quick check

```bash
./jobs/nvidia-smi/run.sh
```

This creates a short Serverless AI Job that runs `nvidia-smi`.

## Authenticated Endpoint quick check

```bash
./endpoints/nginx-auth/run.sh
```

This creates a small public nginx Endpoint with token authentication.
