#!/bin/bash
# This plugin checks if is the VM has the correct number of GPU's

readonly OK=0
readonly NONOK=1
readonly UNKNOWN=2

readonly EXPECTED_NUM_GPU=8

gpu_count=$(nvidia-smi --list-gpus | wc -l)

if [ "$gpu_count" -ne "$EXPECTED_NUM_GPU" ]; then
   echo "Expected to see $EXPECTED_NUM_GPU but found $gpu_count. FaultCode: NHC2009"
   exit $NONOK
else
   echo "Expected $EXPECTED_NUM_GPU and found $gpu_count"
   exit $OK
fi 