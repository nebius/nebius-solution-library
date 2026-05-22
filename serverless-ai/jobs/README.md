# Serverless AI Jobs

Use Jobs for container workloads that should run once and finish. A Job is a better fit than an Endpoint when the work has a clear end: fine-tuning, batch inference, model evaluation, data processing, simulations, or a one-off GPU check.

## How Jobs Behave

- A Job starts a container on the selected `--platform` and `--preset`.
- The container runs until it exits or reaches the configured timeout.
- Compute is released after the Job finishes.
- Output that should survive the run needs to be written somewhere durable, such as Object Storage.
- Logs are available through `nebius ai job logs`.

## Examples

| Example | What it does | When to use it |
| --- | --- | --- |
| [qwen-lora-finetune](./qwen-lora-finetune/README.md) | Runs Axolotl fine-tuning for `Qwen/Qwen2.5-0.5B` and writes LoRA output to Object Storage | Real small training workflow |
| [nvidia-smi](./nvidia-smi/run.sh) | Runs `nvidia-smi` and exits | Quick GPU scheduling and log check |

## Run the Fine-Tuning Job

From the `serverless-ai` directory:

```bash
./jobs/qwen-lora-finetune/prepare.sh
./jobs/qwen-lora-finetune/run.sh
```

Choose a larger platform profile when you want to run the same Job on a different GPU shape:

```bash
./jobs/qwen-lora-finetune/run.sh h200
./jobs/qwen-lora-finetune/run.sh b200
./jobs/qwen-lora-finetune/run.sh b300
```

List supported profiles:

```bash
./jobs/qwen-lora-finetune/run.sh list
```

## Inspect and Clean Up

```bash
nebius ai job get <job_id>
nebius ai job logs <job_id>
nebius ai job delete <job_id>
```
