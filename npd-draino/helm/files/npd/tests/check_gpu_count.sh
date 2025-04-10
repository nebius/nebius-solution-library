#!/bin/bash

# This plugin checks if is the VM has the correct number of GPU's

readonly OK=0
readonly NONOK=1
readonly UNKNOWN=2

readonly EXPECTED_NUM_GPU=8
readonly GPU_TYPE="nvidia"

if [ "$GPU_TYPE" == "rocm" ]; then
   gpu_count=$(rocm-smi -l | grep 'GPU' | wc -l)
else
   gpu_count=$(nvidia-smi --list-gpus | wc -l)
fi

if [ "$gpu_count" -ne "$EXPECTED_NUM_GPU" ]; then
   echo "Expected to see $EXPECTED_NUM_GPU but found $gpu_count. FaultCode: NHC2009"
   exit $NONOK
else
   echo "Expected $EXPECTED_NUM_GPU and found $gpu_count"
   exit $OK
fi 