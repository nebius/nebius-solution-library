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
- Quota for one `gpu-l40s-a` VM with the `1gpu-8vcpu-32gb` preset.
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

Start the fine-tuning job:

```bash
./jobs/qwen-lora-finetune/run.sh
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
