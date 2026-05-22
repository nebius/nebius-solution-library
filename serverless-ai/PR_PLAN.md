# PR Plan: Serverless AI Solution Library Artifacts

## Problem statement

Serverless AI introduces Jobs and Endpoints as a lower-friction path for AI workloads that do not need durable clusters. The current solution library is Terraform-heavy and does not give users a repo-native path to try Serverless AI from the CLI.

## Proposed change

Add a new `serverless-ai/` directory with:

- a root README explaining Jobs, Endpoints, prerequisites, costs, and cleanup;
- separate `jobs/` and `endpoints/` README files that explain the lifecycle differences;
- a `ROOT_README_SNIPPET.md` entry that can be added to the solution library root README;
- shared environment defaults in `environment.sh`;
- a real Qwen LoRA fine-tuning Job under `jobs/qwen-lora-finetune/` with platform-sized profiles;
- an OpenAI-compatible vLLM Endpoint plus support-ticket triage client under `endpoints/vllm-openai/`;
- optional quick checks using the GPU `nvidia-smi` Job and authenticated nginx Endpoint.

## Why CLI-first

The public Serverless AI docs show CLI and console workflows for Jobs and Endpoints. I did not find public Terraform resource documentation for Serverless AI Jobs or Endpoints, so wrapping the Nebius CLI is the lowest-risk solution-library artifact. If Terraform provider support appears later, this directory can gain a Terraform version without blocking the initial examples.

## Validation plan

Static checks:

```bash
bash -n serverless-ai/environment.sh
bash -n serverless-ai/scripts/lib.sh
bash -n serverless-ai/jobs/qwen-lora-finetune/prepare.sh
bash -n serverless-ai/jobs/qwen-lora-finetune/run.sh
bash -n serverless-ai/jobs/nvidia-smi/run.sh
bash -n serverless-ai/endpoints/nginx-auth/run.sh
bash -n serverless-ai/endpoints/vllm-openai/run.sh
bash -n serverless-ai/endpoints/vllm-openai/run-triage.sh
python3 -m py_compile serverless-ai/endpoints/vllm-openai/triage_client.py
```

Live checks in a Nebius project with quota:

```bash
source serverless-ai/environment.sh
./serverless-ai/jobs/qwen-lora-finetune/prepare.sh
./serverless-ai/jobs/qwen-lora-finetune/run.sh
./serverless-ai/endpoints/vllm-openai/run.sh
./serverless-ai/endpoints/vllm-openai/run-triage.sh
```

Then confirm:

- Fine-tuning Job logs show Axolotl training progress.
- Object Storage contains LoRA adapter output under `output/run-.../`.
- vLLM `/v1/chat/completions` returns triage JSON for the sample tickets.
- Endpoint resources are deleted after validation.

## Risks

- Serverless AI is public-preview functionality, so CLI flags may change.
- vLLM startup depends on Hugging Face model download availability and regional GPU quota.
- The Axolotl fine-tuning example depends on the public Axolotl image and Hugging Face dataset/model availability.
- Endpoints bill until stopped or deleted.

## Expected KPI impact

- Enhancing out-of-the-box solutions: gives users a first-run path for new Serverless AI services.
- Customer satisfaction: reduces repeated explanation for "how do I try Jobs or Endpoints?"
- Product offering feedback: creates a concrete place to capture gaps such as Terraform support.
