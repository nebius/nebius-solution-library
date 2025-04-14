#docker build -t registry/image . --platform linux/amd64
#docker push registry/image
FROM registry.k8s.io/node-problem-detector/node-problem-detector:v0.8.20 AS node-problem-detector

FROM nvidia/cuda:12.3.2-runtime-ubuntu22.04

# Make apt-get non-interactive
ENV DEBIAN_FRONTEND=noninteractive

# Install minimal required packages
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    procps \
    iproute2 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy the node-problem-detector binary from the first stage
COPY --from=node-problem-detector /node-problem-detector /node-problem-detector

# Set environment variables
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=$PATH:$CUDA_HOME/bin
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$CUDA_HOME/lib64

# Set working directory
WORKDIR /
