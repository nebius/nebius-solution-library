import os
import math
import boto3
import torch
import torch.distributed as dist
from collections import defaultdict
from boto3.s3.transfer import TransferConfig

def list_objects(bucket, prefix=""):
    """List all object keys in the given S3 bucket with an optional prefix."""
    session = boto3.Session(profile_name=os.environ.get('SOURCE_PROFILE'))
    s3 = session.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
    keys = []
    for page in pages:
        if 'Contents' in page:
            for obj in page['Contents']:
                keys.append(obj['Key'])
    return keys

def verify_object_exists(bucket, key):
    """Verify that an object exists in the specified bucket."""
    session = boto3.Session(profile_name=os.environ.get('TARGET_PROFILE'))
    s3 = session.client('s3')
    try:
        if key.endswith('/'):  # For directory objects
            resp = s3.list_objects_v2(Bucket=bucket, Prefix=key, MaxKeys=1)
            # If the directory exists, it should have the exact key or contain objects with this prefix
            return 'Contents' in resp and (
                any(obj['Key'] == key for obj in resp['Contents']) or 
                len(resp.get('Contents', [])) > 0
            )
        else:
            # For regular objects, a head_object check is sufficient
            s3.head_object(Bucket=bucket, Key=key)
            return True
    except Exception as e:
        # Change error message to be clearer that this is just a check, not an actual error
        print(f"Object {key} not found in target bucket, will copy it: {str(e)}")
        return False

def local_file_exists_and_matches(key, target_bucket):
    """Check if a local temp file exists and has the same size as the target S3 object."""
    # Handle directory objects (keys ending with '/')
    if key.endswith('/'):
        return False  # Always recreate directory markers
    
    # Create temp filename
    temp_dir = os.path.join(os.getcwd(), "temp_downloads")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Handle potential empty basename
    basename = os.path.basename(key) or "empty_file"
    local_path = os.path.join(temp_dir, basename)
    
    if not os.path.exists(local_path):
        return False
        
    # If we have a local file, check if target already has it
    try:
        session = boto3.Session(profile_name=os.environ.get('TARGET_PROFILE'))
        s3 = session.client('s3')
        response = s3.head_object(Bucket=target_bucket, Key=key)
        
        # Compare size with local file
        if os.path.getsize(local_path) == response['ContentLength']:
            return True
    except Exception:
        # In case of any error, we'll re-download
        pass
    
    return False

def copy_object(source_bucket, target_bucket, key):
    """Copy a single S3 object from the source bucket to the target bucket using multipart."""
    source_session = boto3.Session(profile_name=os.environ.get('SOURCE_PROFILE'))
    target_session = boto3.Session(profile_name=os.environ.get('TARGET_PROFILE'))
    source_s3 = source_session.client('s3')
    target_s3 = target_session.client('s3')
    
    # Handle directory objects (keys ending with '/') by creating empty objects
    if key.endswith('/'):
        try:
            print(f"Creating directory marker object {key}")
            # For directories, just put an empty object with the same key
            target_s3.put_object(Bucket=target_bucket, Key=key, Body='')
            print(f"Created directory marker for {key}")
            return True
        except Exception as e:
            print(f"Failed to create directory marker for {key}: {e}")
            return False
    
    # Skip if already in the target bucket
    if verify_object_exists(target_bucket, key):
        print(f"Object {key} already exists in target bucket, skipping.")
        return True
    
    print(f"Copying object {key} to target bucket...")
    
    try:
        # Get object size to determine if multipart is appropriate
        response = source_s3.head_object(Bucket=source_bucket, Key=key)
        object_size = response['ContentLength']
        
        # Create a temporary directory for downloads if it doesn't exist
        temp_dir = os.path.join(os.getcwd(), "temp_downloads")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Create proper directory structure for the file
        basename = os.path.basename(key) or "empty_file"  # Handle empty basename
        temp_file = os.path.join(temp_dir, basename)

        if object_size < 10 * 1024 * 1024:  # Less than 10MB
            print(f"Small file detected ({object_size} bytes), using single-part transfer for {key}")
            
            # Download with standard method
            source_s3.download_file(Bucket=source_bucket, Key=key, Filename=temp_file)
            
            # Upload with standard method
            target_s3.upload_file(Filename=temp_file, Bucket=target_bucket, Key=key)
        else:
            # Configure multipart transfers for larger files
            # Ensure chunk size is appropriate for the file size to avoid EntityTooSmall errors
            # S3 requires at least 5MB per part (except the last part)
            chunk_size = max(8 * 1024 * 1024, (object_size // 10000) + 1)  # Ensure chunks aren't too small
            
            config = TransferConfig(
                multipart_threshold=8 * 1024 * 1024,  # Start multipart at 8MB
                max_concurrency=10,                  # Concurrent operations
                multipart_chunksize=chunk_size,     # Dynamically sized chunks
                use_threads=True
            )
            
            # Check if we have a partially downloaded file already
            if local_file_exists_and_matches(key, target_bucket):
                print(f"Local file for {key} already exists, skipping download.")
            else:
                # Download from source to local temp file
                print(f"Downloading {key} to local temp file")
                source_s3.download_file(
                    Bucket=source_bucket,
                    Key=key,
                    Filename=temp_file,
                    Config=config
                )
            
            # Upload from local to target
            print(f"Uploading {key} to target bucket")
            target_s3.upload_file(
                Filename=temp_file,
                Bucket=target_bucket,
                Key=key,
                Config=config
            )
        
        print(f"Successfully copied {key}")
        return True
    except Exception as e:
        print(f"Failed to copy {key}: {e}")
        return False

def main():
    # Initialize the distributed process group.
    # Expecting environment variables to be set by torchrun (or via a launcher like SkyPilot).
    dist.init_process_group(backend='gloo', init_method='env://')
    rank = dist.get_rank()
    world_size = dist.get_world_size()

    # Get bucket names and prefix from environment variables.
    source_bucket = os.environ.get('SOURCE_BUCKET')
    target_bucket = os.environ.get('TARGET_BUCKET')
    prefix = os.environ.get('PREFIX', "")

    # Tracking for successful and failed transfers
    successful_transfers = []
    failed_transfers = []

    # Rank 0 lists all objects in the source bucket.
    if rank == 0:
        print("Listing objects from source bucket...")
        objects = list_objects(source_bucket, prefix)
    else:
        objects = None

    # Broadcast the object list from rank 0 to all processes.
    # torch.distributed.broadcast_object_list requires a pre-allocated list.
    object_list = [objects] if rank == 0 else [None]
    dist.broadcast_object_list(object_list, src=0)
    objects = object_list[0]

    if objects is None:
        print("No objects found or error in broadcast.")
        return

    total_objects = len(objects)
    print(f"Rank {rank}: Received {total_objects} objects for migration.")

    # Partition the list among the ranks.
    chunk_size = math.ceil(total_objects / world_size)
    start = rank * chunk_size
    end = min(start + chunk_size, total_objects)
    my_keys = objects[start:end]
    print(f"Rank {rank}: Processing objects {start} to {end}.")

    # Each process copies its assigned objects.
    for key in my_keys:
        try:
            success = copy_object(source_bucket, target_bucket, key)
            if success:
                # Verify the object was successfully copied
                if verify_object_exists(target_bucket, key):
                    successful_transfers.append(key)
                else:
                    print(f"Rank {rank}: Object {key} was not found in target bucket after copy")
                    failed_transfers.append(key)
            else:
                failed_transfers.append(key)
        except Exception as e:
            print(f"Rank {rank}: Failed to copy {key}: {e}")
            failed_transfers.append(key)

    # Gather results from all processes
    all_successful = [None] * world_size
    all_failed = [None] * world_size
    
    dist.all_gather_object(all_successful, successful_transfers)
    dist.all_gather_object(all_failed, failed_transfers)

    # Ensure all processes finish before final verification
    dist.barrier()
    
    if rank == 0:
        # Flatten the lists
        all_successful_flat = [key for sublist in all_successful for key in sublist]
        all_failed_flat = [key for sublist in all_failed for key in sublist]
        
        # Generate verification report
        print("\n=== S3 MIGRATION VERIFICATION REPORT ===")
        print(f"Total objects to transfer: {total_objects}")
        print(f"Successfully transferred: {len(all_successful_flat)}")
        print(f"Failed transfers: {len(all_failed_flat)}")
        
        # Calculate success rate
        success_rate = (len(all_successful_flat) / total_objects) * 100 if total_objects > 0 else 0
        print(f"Success rate: {success_rate:.2f}%")
        
        # Report failed transfers if any
        if all_failed_flat:
            print("\nFailed transfers:")
            for key in all_failed_flat:
                print(f"  - {key}")
            
            # Save failed transfers to a file for retry
            with open("failed_transfers.txt", "w") as f:
                for key in all_failed_flat:
                    f.write(f"{key}\n")
            print(f"\nFailed transfers saved to failed_transfers.txt")
            
        # Final verification of all objects
        print("\nPerforming final verification of all objects...")
        print("Checking a sample of successful transfers...")
        
        verification_issues = []
        for key in all_successful_flat:
            if not verify_object_exists(target_bucket, key):
                verification_issues.append(key)
        
        if verification_issues:
            print(f"Warning: {len(verification_issues)} objects reported as successful were not found in final verification")
            print("Migration may have had issues. Consider running a full verification.")
        else:
            print("Sample verification completed successfully!")
        
        # Overall status
        if len(all_failed_flat) == 0 and len(verification_issues) == 0:
            print("\nS3 migration completed successfully on all nodes.")
        else:
            print("\nS3 migration completed with issues. See report above.")

if __name__ == '__main__':
    main()