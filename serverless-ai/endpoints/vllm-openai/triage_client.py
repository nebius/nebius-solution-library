#!/usr/bin/env python3

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_env_file(path):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def parse_model_json(content):
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise
        return json.loads(content[start : end + 1])


def post_chat(endpoint_url, token, model, ticket):
    prompt = (
        "You are a solutions architect triaging Nebius AI Cloud support tickets. "
        "Return compact JSON only with keys priority, category, summary, next_action. "
        "Priority must be one of P0, P1, P2, P3.\n\n"
        f"Ticket:\n{json.dumps(ticket, ensure_ascii=True)}"
    )
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    }
    request = urllib.request.Request(
        endpoint_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"endpoint returned HTTP {exc.code}: {detail}") from exc
    content = body["choices"][0]["message"]["content"].strip()
    return parse_model_json(content)


def iter_jsonl(path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def main():
    default_env = Path(__file__).with_name(".endpoint.env")
    env_file = Path(os.environ.get("SERVERLESS_ENDPOINT_ENV", default_env))
    env = load_env_file(env_file)

    parser = argparse.ArgumentParser(description="Triage support tickets with a vLLM endpoint.")
    parser.add_argument("--endpoint-url", default=os.environ.get("ENDPOINT_URL") or env.get("ENDPOINT_URL"))
    parser.add_argument("--endpoint-ip", default=os.environ.get("ENDPOINT_IP") or env.get("ENDPOINT_IP"))
    parser.add_argument("--token", default=os.environ.get("AUTH_TOKEN") or env.get("AUTH_TOKEN"))
    parser.add_argument("--model", default=os.environ.get("MODEL_ID") or env.get("MODEL_ID") or "Qwen/Qwen3-0.6B")
    parser.add_argument("--tickets", type=Path, default=Path(__file__).with_name("sample-tickets.jsonl"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("output") / "triage-results.jsonl")
    args = parser.parse_args()

    endpoint_url = args.endpoint_url
    if not endpoint_url and args.endpoint_ip:
        endpoint_url = f"http://{args.endpoint_ip}"
    if not endpoint_url or not args.token:
        print("Missing endpoint URL/IP or AUTH_TOKEN. Run ./endpoints/vllm-openai/run.sh first.", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        for ticket in iter_jsonl(args.tickets):
            triage = post_chat(endpoint_url, args.token, args.model, ticket)
            output.write(json.dumps({"ticket_id": ticket["id"], "triage": triage}, ensure_ascii=True) + "\n")

    print(f"Wrote triage results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
