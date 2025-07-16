FROM rayproject/ray:nightly-py39-cpu

# Add your training script
COPY train.py /app/train.py

WORKDIR /app

# The sleep infinity command keeps the container running and make it available for the Ray cluster.
# It keeps the Ray Head and Worker containers alive and ready to receive tasks.
# Make sure to use Ray Operator to manage the Ray cluster lifecycle.
CMD ["sleep", "infinity"]
