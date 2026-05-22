# Serverless AI

Serverless AI on Nebius AI Cloud runs containerized AI workloads without asking users to create and operate long-lived VM fleets or clusters. The public documentation currently covers two deployable surfaces:

- **Jobs**: finite workloads that start, run to completion or timeout, and release compute resources. Good fits include batch processing, training experiments, fine-tuning, model evaluation, and scientific simulations.
- **Endpoints**: persistent HTTP services for interactive workloads such as custom model serving, inference pipeline validation, A/B testing, and OpenAI-compatible model backends.

Nebius' product page also describes **DevPods** as interactive development environments with Jupyter and VS Code for exploratory analysis, model prototyping, and debugging. As of this artifact, the docs and CLI quickstarts are available for Jobs and Endpoints, while DevPods should stay as a tracked follow-up until public deployment documentation is available.

## Why this belongs in the solution library

Most existing solution-library examples provision durable infrastructure with Terraform. Serverless AI is different: the public workflow is CLI-first today, and the value is a thin, repeatable wrapper around the documented commands. This directory gives users a repo-shaped entry point for:

- running a small Qwen LoRA fine-tuning Job with Axolotl and Object Storage output;
- launching a small OpenAI-compatible vLLM Endpoint;
- using that Endpoint for support-ticket triage;
- optionally testing logs, auth, GPU scheduling, and endpoint traffic with quick checks;
- deleting resources when validation is complete.

## Prerequisites

- Nebius AI Cloud CLI installed and configured for the target project.
- A project with the required Compute and VPC quotas.
- At least one subnet in the target region.
- `curl` for Endpoint validation.
- `openssl` for token generation.
- AWS CLI for Object Storage examples.

For GPU examples, make sure the selected region has quota for the requested platform and preset.

## Configure

Copy and edit the defaults:

```bash
cp environment.sh .env.serverless-ai
$EDITOR .env.serverless-ai
source .env.serverless-ai
```

The examples default to `default-subnet`, `gpu-l40s-a`, and `1gpu-8vcpu-32gb` because those match the public quickstarts. Override them when your region or quota differs.

## Real Examples

### Fine-tune Qwen with a Serverless AI Job

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

### Deploy a vLLM Endpoint and triage support tickets

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

Each script prints the exact delete command for the resource it created. Jobs release compute resources after completion, but deleting the Job removes it from the list. Endpoints keep running and billing until stopped or deleted.

## Source references

- Serverless AI overview: https://docs.nebius.com/serverless/overview
- Jobs quickstart: https://docs.nebius.com/serverless/quickstart/jobs
- Endpoints quickstart: https://docs.nebius.com/serverless/quickstart/endpoints
- vLLM Endpoint tutorial: https://docs.nebius.com/serverless/tutorials/deploy-model
- Fine-tuning with Axolotl tutorial: https://docs.nebius.com/serverless/tutorials/fine-tuning
- Pricing and quotas: https://docs.nebius.com/serverless/pricing-quotas
- Product positioning, including DevPods: https://nebius.com/services/serverless
