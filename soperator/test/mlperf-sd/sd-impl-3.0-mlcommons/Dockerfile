ARG FROM_IMAGE_NAME=nvcr.io/nvidia/pytorch:22.12-py3
FROM ${FROM_IMAGE_NAME}

ENV DEBIAN_FRONTEND=noninteractive

# apt dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg libsm6 libxext6 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# install LDM
COPY . /diffusion
RUN cd /diffusion && \
    python -m pip install --upgrade pip && \
    python -m pip uninstall --no-cache-dir -y opencv-python opencv-python-headless && \
    rm -rf /usr/local/lib/python3.8/dist-packages/opencv-* /usr/local/lib/python3.8/dist-packages/cv2 && \
    python -m pip uninstall --no-cache-dir -y spacy typer && \
    python -m pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip
