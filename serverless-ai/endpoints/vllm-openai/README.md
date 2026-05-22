# OpenAI-Compatible vLLM Endpoint

This example deploys a small OpenAI-compatible model backend with Serverless AI Endpoints and then uses it for a concrete application: support-ticket triage.

The endpoint runs `vllm/vllm-openai:v0.18.0-cu130` with `Qwen/Qwen3-0.6B` by default. The client reads sample tickets from JSONL, asks the endpoint to classify each item, and writes JSONL output with priority, category, summary, and next action.

Use this when you need a real Endpoint example. It is not a batch Job: the container stays up, exposes an HTTP API, and should be deleted when testing is done.

## What it does

1. Creates a token-authenticated public Endpoint.
2. Runs vLLM with an OpenAI-compatible API server.
3. Writes the Endpoint ID, address, token, and model ID to `.endpoint.env`.
4. Sends sample support tickets to `/v1/chat/completions`.
5. Writes triage results to `output/triage-results.jsonl`.

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
