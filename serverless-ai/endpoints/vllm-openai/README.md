# OpenAI-Compatible vLLM Endpoint

This example deploys a small OpenAI-compatible model backend with Serverless AI Endpoints and then uses it for a concrete application: support-ticket triage.

The endpoint runs `vllm/vllm-openai:v0.18.0-cu130` with `Qwen/Qwen3-0.6B` by default. The client reads sample tickets from JSONL, asks the endpoint to classify each item, and writes JSONL output with priority, category, summary, and next action.

## Deploy

From the `serverless-ai` root:

```bash
cp environment.sh .env.serverless-ai
$EDITOR .env.serverless-ai
source .env.serverless-ai
./endpoints/vllm-openai/run.sh
```

The deploy script writes connection details to:

```text
endpoints/vllm-openai/.endpoint.env
```

Wait until the endpoint status is `Running`:

```bash
nebius ai endpoint get <endpoint_id>
```

## Run the triage client

```bash
./endpoints/vllm-openai/run-triage.sh
```

The output is written to:

```text
endpoints/vllm-openai/output/triage-results.jsonl
```

## Cleanup

Endpoints keep billing until deleted:

```bash
source endpoints/vllm-openai/.endpoint.env
nebius ai endpoint delete "$ENDPOINT_ID"
```
