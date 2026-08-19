FROM vllm/vllm-openai@sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d

WORKDIR /workspace
EXPOSE 8000

CMD ["--model", "zai-org/GLM-5.2-FP8", "--revision", "ba978f7d347eaf65d22f1a86833408afdb953541", "--served-model-name", "zai-org/GLM-5.2-FP8", "--tensor-parallel-size", "8", "--max-model-len", "131072", "--reasoning-parser", "glm45", "--tool-call-parser", "glm47", "--enable-auto-tool-choice", "--no-enable-prefix-caching", "--port", "8000"]
