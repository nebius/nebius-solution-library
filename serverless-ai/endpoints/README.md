# Serverless AI Endpoints

Use Endpoints for container workloads that need to stay online and receive HTTP requests. An Endpoint is a better fit than a Job when another system, user, or demo needs to call the workload repeatedly.

## How Endpoints Behave

- An Endpoint starts a container on the selected `--platform` and `--preset`.
- It exposes one or more container ports.
- It can be public and token-authenticated.
- It keeps running until you delete it.
- Logs are available through `nebius ai endpoint logs`.

## Examples

| Example | What it does | When to use it |
| --- | --- | --- |
| [vllm-openai](./vllm-openai/README.md) | Serves `Qwen/Qwen3-0.6B` through vLLM's OpenAI-compatible API and runs a support-ticket triage client | Real small inference service |
| [nginx-auth](./nginx-auth/run.sh) | Starts nginx with token auth | Quick public networking and auth check |

## Deploy the vLLM Endpoint

From the `serverless-ai` directory:

```bash
./endpoints/vllm-openai/run.sh
```

Wait for the Endpoint to become `Running`, then run the sample client:

```bash
./endpoints/vllm-openai/run-triage.sh
```

## Inspect and Clean Up

```bash
nebius ai endpoint get <endpoint_id>
nebius ai endpoint logs <endpoint_id>
nebius ai endpoint delete <endpoint_id>
```

Endpoints keep running until deleted, so clean them up when the test is done.
