rclone sync s3mlperf:renes-bucket /datasets \
	--progress --links \
	--use-mmap \
	--bwlimit=1000M \
	--transfers=64 --buffer-size=512Mi \
	--multi-thread-streams=24 --multi-thread-chunk-size=128Mi --multi-thread-cutoff=4Gi --multi-thread-write-buffer-size=256Mi \
	--checkers=16 --size-only \
	--update --use-server-modtime --fast-list --s3-no-head-object --s3-chunk-size=32M


.config/rclone/rclone.conf
[s3mlperf]
type = s3
provider = AWS
env_auth = false
region = eu-north1
no_check_bucket = true
endpoint = https://storage.eu-north1.nebius.cloud:443
acl = private
bucket_acl = private
access_key_id = NAKI50IKWMRP76VI9Y7K
secret_access_key = sqMJyY/xvvCVDdIrfcKzn28651GE32WwUK3SqKqr

# Data Transfer
This repository contains solutions for high-performance data transfer between Amazon S3 and local file storage across multiple nodes. The primary script provided is copy_s3_to_sfs_multi_node.sh, which enables efficient data synchronization.

## From S3 to file system / File system to S3

Script: copy_s3_to_sfs_multi_node.sh

This script facilitates file transfers:

From S3 to local file storage

From local file storage to S3

Across multiple nodes simultaneously

It operates with or without SLURM, as long as SSH access to the nodes is available.

### Configuration


1. Define worker nodes: Specify the nodes that should be used in the script by modifying the NODES array: 
```
NODES=("worker-0" "worker-1" "worker-2" "worker-3")
```

Nodes can be identified by either IP addresses or hostnames.


2. S3 Configuration

Ensure that the S3 configuration is correctly set up in `~/.config/rclone/rclone.conf`. Below is an example configuration:

```
[s3]
type = s3
provider = AWS
env_auth = false
region = eu-north1
no_check_bucket = true
endpoint = https://storage.eu-north1.nebius.cloud:443
acl = private
bucket_acl = private
access_key_id = xxx
secret_access_key = xxx
```


### On slurm

### On k8s

### On vm instances



## From S3 to S3

### On slurm

### On k8s

### On vm instances


## From SFS to SFS

### On slurm

### On k8s

### On vm instances

# Benchmarks

