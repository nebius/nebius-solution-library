ARG BASE_IMAGE=cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/qwen-vllm-placeholder@sha256:5d665359fe5f49d6adaedd5856e886598a77e4fd099b34b0a6718f041ce9b1e2
FROM ${BASE_IMAGE}

RUN python3 -m pip install --no-cache-dir --no-deps diffusers==0.39.0 \
    && python3 -c 'import diffusers; assert diffusers.__version__ == "0.39.0"'

COPY server.py /opt/k301ud/sdxl_server.py

ENTRYPOINT ["/usr/bin/python3", "/opt/k301ud/sdxl_server.py"]
