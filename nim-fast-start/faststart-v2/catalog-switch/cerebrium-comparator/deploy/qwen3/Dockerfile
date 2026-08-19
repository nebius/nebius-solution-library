FROM vllm/vllm-openai@sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d

WORKDIR /workspace
EXPOSE 8000

CMD ["--model", "Qwen/Qwen3-8B", "--revision", "b968826d9c46dd6066d109eabc6255188de91218", "--served-model-name", "Qwen/Qwen3-8B", "--dtype", "bfloat16", "--tensor-parallel-size", "1", "--max-model-len", "32768", "--reasoning-parser", "qwen3", "--port", "8000"]
