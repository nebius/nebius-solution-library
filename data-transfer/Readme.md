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

## From S3 to SFS

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

