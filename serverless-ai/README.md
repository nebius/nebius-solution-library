# Serverless AI

Serverless AI on Nebius AI Cloud runs containerized AI workloads without asking users to create and operate long-lived VM fleets or clusters.

There are two different execution models in this directory. Pick one before you run anything:

| Use this | When you need | Lifecycle | Example |
| --- | --- | --- | --- |
| [Jobs](./jobs/README.md) | A finite run that should finish and release compute | Starts, runs to completion or timeout, then stops | Fine-tune Qwen with Axolotl |
| [Endpoints](./endpoints/README.md) | A service that accepts HTTP requests | Stays up until you delete it | Serve Qwen through vLLM and triage sample tickets |

## Directory Layout

| Path | Purpose |
| --- | --- |
| [jobs/qwen-lora-finetune](./jobs/qwen-lora-finetune/README.md) | Real Serverless AI Job: fine-tunes `Qwen/Qwen2.5-0.5B` with Axolotl and writes LoRA output to Object Storage |
| [endpoints/vllm-openai](./endpoints/vllm-openai/README.md) | Real Serverless AI Endpoint: serves `Qwen/Qwen3-0.6B` through vLLM and runs a support-ticket triage client |

## Prerequisites

- Nebius AI Cloud CLI installed and configured for the target project.
- A project with the required Compute and VPC quotas.
- At least one subnet in the target region.
- `curl` for Endpoint validation.
- `openssl` for token generation.
- AWS CLI for Object Storage examples.

For GPU examples, make sure the selected region has quota for the requested platform and preset.

## Common Configuration

Copy and edit the defaults:

```bash
cp environment.sh .env.serverless-ai
$EDITOR .env.serverless-ai
source .env.serverless-ai
```

The examples default to `default-subnet`, `gpu-l40s-a`, and `1gpu-8vcpu-32gb`. Override them when your region or quota differs.

## Run a Job

Use Jobs for work that should finish. The fine-tuning example creates a Job, mounts Object Storage, runs Axolotl, copies output back to the bucket, and exits.

```bash
./jobs/qwen-lora-finetune/prepare.sh
./jobs/qwen-lora-finetune/run.sh
```

This example runs a real Axolotl fine-tuning workload against `Qwen/Qwen2.5-0.5B`, saves LoRA adapter output to Object Storage, and keeps the run bounded at 30 steps. The same job can be launched on platform-sized profiles:

```bash
./jobs/qwen-lora-finetune/run.sh h100
./jobs/qwen-lora-finetune/run.sh h200
./jobs/qwen-lora-finetune/run.sh b200
./jobs/qwen-lora-finetune/run.sh rtx6000
./jobs/qwen-lora-finetune/run.sh l40s-d
```

The `h100`, `h200`, `b200`, `b200-a`, `b300`, and `rtx6000` profiles use 8-GPU presets. L40S does not have a documented 8-GPU preset, so `l40s-d` uses the largest documented L40S shape.

## Deploy an Endpoint

Use Endpoints for services that should stay online and receive HTTP requests. The vLLM example creates an Endpoint, writes connection details to a local `.endpoint.env` file, and then a separate client sends sample support tickets to the OpenAI-compatible API.

```bash
./endpoints/vllm-openai/run.sh
```

After the endpoint status is `Running`:

```bash
./endpoints/vllm-openai/run-triage.sh
```

This example deploys an OpenAI-compatible vLLM backend for `Qwen/Qwen3-0.6B`, then classifies sample support tickets into priority, category, summary, and next action.

## Quick Checks

Use these when you want to validate the environment before running the real examples.

### Run a GPU smoke-test Job

```bash
./jobs/nvidia-smi/run.sh
```

### Run an authenticated nginx Endpoint

```bash
./endpoints/nginx-auth/run.sh
```

## Cleanup

Each script prints the delete command for the resource it created.

- Jobs release compute resources after completion. Delete the Job record when you no longer need it in the Job list.
- Endpoints keep running until deleted. Delete them when you finish testing.

## Source references

- Serverless AI overview: https://docs.nebius.com/serverless/overview
- Jobs quickstart: https://docs.nebius.com/serverless/quickstart/jobs
- Endpoints quickstart: https://docs.nebius.com/serverless/quickstart/endpoints
- vLLM Endpoint tutorial: https://docs.nebius.com/serverless/tutorials/deploy-model
- Fine-tuning with Axolotl tutorial: https://docs.nebius.com/serverless/tutorials/fine-tuning
- Pricing and quotas: https://docs.nebius.com/serverless/pricing-quotas
