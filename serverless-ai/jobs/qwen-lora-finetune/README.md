# Qwen LoRA Fine-Tuning Job

This example runs a small but real fine-tuning workload with Serverless AI Jobs. It uses the public Axolotl container image from the Nebius tutorial, fine-tunes `Qwen/Qwen2.5-0.5B` for 30 steps with QLoRA, and writes adapter output to Object Storage.

Use this when you want to show more than a GPU smoke test while keeping the runtime and cost bounded.

## What it does

1. Creates or reuses an Object Storage bucket.
2. Uploads `config.yaml` to the bucket.
3. Runs a Serverless AI Job with the Axolotl image.
4. Mounts the bucket at `/workspace/data`.
5. Saves LoRA adapter output under `s3://<bucket>/output/run-.../`.

## Prerequisites

- Nebius AI Cloud CLI configured for the target project.
- AWS CLI configured for Nebius Object Storage.
- Quota for the selected GPU platform and preset.
- A subnet available in the target region.

## Configure

From the `serverless-ai` root:

```bash
cp environment.sh .env.serverless-ai
$EDITOR .env.serverless-ai
source .env.serverless-ai
```

Set `SERVERLESS_FINE_TUNE_BUCKET` to a bucket name that is available in your project.

## Run

Prepare the bucket and upload the Axolotl config:

```bash
./jobs/qwen-lora-finetune/prepare.sh
```

Start the default low-cost L40S fine-tuning job:

```bash
./jobs/qwen-lora-finetune/run.sh
```

Start the same job on a larger platform profile:

```bash
./jobs/qwen-lora-finetune/run.sh h100
./jobs/qwen-lora-finetune/run.sh h200
./jobs/qwen-lora-finetune/run.sh b200
./jobs/qwen-lora-finetune/run.sh b200-a
./jobs/qwen-lora-finetune/run.sh rtx6000
```

List all profiles:

```bash
./jobs/qwen-lora-finetune/run.sh list
```

## Profiles

| Profile | Platform | Preset | Notes |
| --- | --- | --- | --- |
| `l40s-a` | `gpu-l40s-a` | `1gpu-8vcpu-32gb` | Default low-cost profile |
| `l40s-d` | `gpu-l40s-d` | `4gpu-192vcpu-1152gb` | Largest documented L40S profile |
| `b200` | `gpu-b200-sxm` | `8gpu-160vcpu-1792gb` | 8-GPU B200 profile |
| `b200-a` | `gpu-b200-sxm-a` | `8gpu-160vcpu-1792gb` | 8-GPU B200 profile for the alternate B200 platform |
| `b300` | `gpu-b300-sxm` | `8gpu-192vcpu-2768gb` | 8-GPU B300 profile |
| `h100` | `gpu-h100-sxm` | `8gpu-128vcpu-1600gb` | 8-GPU H100 profile |
| `h200` | `gpu-h200-sxm` | `8gpu-128vcpu-1600gb` | 8-GPU H200 profile |
| `rtx6000` | `gpu-rtx6000` | `8gpu-192vcpu-1744gb` | 8-GPU RTX PRO 6000 profile |

Public docs do not list an 8-GPU L40S preset; the largest L40S profile here uses `gpu-l40s-d` with `4gpu-192vcpu-1152gb`. Public docs also do not list a B100 platform ID. If your project exposes B100, use the custom profile:

```bash
SERVERLESS_FINE_TUNE_PLATFORM=<b100-platform-id> \
SERVERLESS_FINE_TUNE_PRESET=<b100-preset> \
./jobs/qwen-lora-finetune/run.sh custom
```

Watch job status and logs:

```bash
nebius ai job get <job_id>
nebius ai job logs <job_id>
```

## Results

The job writes output to:

```text
s3://$SERVERLESS_FINE_TUNE_BUCKET/output/run-<timestamp>/
```

Download a checkpoint file with:

```bash
aws s3 cp s3://$SERVERLESS_FINE_TUNE_BUCKET/output/<run_id>/checkpoint-30/adapter_config.json \
  jobs/qwen-lora-finetune/download/adapter_config.json
```

## Cleanup

Jobs release compute resources after completion. Delete the job record when you no longer need it:

```bash
nebius ai job delete <job_id>
```

Delete the bucket only after you have downloaded any result artifacts you want to keep.
