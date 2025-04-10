#!/bin/bash
# This plugin checks if is the GPU NVlink is working correctly.

readonly OK=0
readonly NONOK=1
readonly UNKNOWN=2

readonly EXPECTED_NUM_GPU=8

# Check if nvlink is enabled
num_gpus=$EXPECTED_NUM_GPU

nvlink_status=$(nvidia-smi nvlink --status)
if [ $? -ne 0 ]; then
   echo "Failed to get NVLINK status with error code $?. FaultCode: NHC2016"
   exit $NONOK
fi
if [ -z "$nvlink_status" ]; then
   echo "NVLINK is not enabled"
   exit $OK
fi
for ((i=0; i<num_gpus; i++)); do
    gpu_id=$i
# Run nvlink command
    nvlink_output=$(nvidia-smi nvlink -s -i $gpu_id)
    if [ $? -ne 0 ]; then
       echo "Failed to get NVLINK status with error code $?. FaultCode: NHC2016"
       exit $NONOK
    fi
 # Check for inactive links
    if [[ $nvlink_output == *"inactive"* ]]; then
 # Extract and display the information about inactive links
       inactive_links=$(echo "$nvlink_output" | grep "Link" | grep "<inactive>" | sed 's/Link \([0-9]*\): <inactive>/Link \1: Inactive/')
       echo "GPU $gpu_id has nvlinks inactive: $inactive_links. FaultCode: NHC2016"
       exit 1
    elif [[ $nvlink_output == *"all links are inActive"* ]]; then
         echo "GPU $gpu_id has all nvlinks inactive"
         exit 1
    else
         echo "GPU $gpu_id has all nvlinks active."
         exit $OK
    fi
    echo "NVLink is enabled and GPU $gpu_id has all nvlinks active"
    exit $OK
done

exit 0 