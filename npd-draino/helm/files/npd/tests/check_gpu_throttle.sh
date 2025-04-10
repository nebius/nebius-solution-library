#!/bin/bash
# This plugin checks GPU throttling

readonly GPU_CLOCKS_THROTTLE_REASON_HW_SLOWDOWN=0x0000000000000008
readonly GPU_CLOCKS_THROTTLE_REASON_HW_THERMAL_SLOWDOWN=0x000000000000004
readonly GPU_CLOCKS_THROTTLE_REASON_APPLICATIONS_CLOCK_SETTINGS=0x0000000000000002
readonly GPU_CLOCKS_THROTTLE_READON_DISPLAY_SETTINGS=0x0000000000000100
readonly GPU_CLOCKS_THROTTLE_REASON_GPU_IDLE=0x0000000000000001
readonly GPU_CLOCKS_THROTTLE_REASON_POWER_BRAKE_SLOWDOWN=0x0000000000000080
readonly GPU_CLOCKS_THROTTLE_REASON_NONE=0x0000000000000000
readonly GPU_CLOCKS_THROTTLE_REASON_SW_POWER_CAP=0x0000000000000004
readonly GPU_CLOCKS_THROTTLE_REASON_SW_THERMAL_SLOWDOWN=0x0000000000000020
readonly GPU_CLOCKS_THROTTLE_REASON_SYNC_BOOST=0x0000000000000010

function collect_gpu_clock_throttle_data() {
# build proper command based on nvidia-smi version
   desired_version="535.54.03"
   nvidia_smi_version=$(nvidia-smi --id=0 --query-gpu=driver_version --format=csv,noheader)
   if [[ "$(echo -e "$nvidia_smi_version\n$desired_version" | sort -V | head -n1)" == "$desired_version" ]]; then
     GPU_THROTTLE_QUERY="clocks_event_reasons.active"
   else
     GPU_THROTTLE_QUERY="clocks_throttle_reasons.active"
   fi

   gpu_clock_throttle_query_out=$(nvidia-smi --query-gpu=$GPU_THROTTLE_QUERY --format=csv,noheader,nounits)
   gpu_clock_throttle_query_rc=$?
   if [[ $gpu_clock_throttle_query_rc != 0 ]]; then
      echo "$gpu_clock_throttle_query_out"
      echo "Warning GPU throttle check test failed to run. In most cases this is due to nvidia-smi query options not being available in the installed version. The reported return code is $gpu_clock_throttle_query_rc. The remainder of the tests will continue."
      exit 0
   fi
#  echo "gpu_clock_throttle_query_out=$gpu_clock_throttle_query_out"
   IFS=$'\n'
   gpu_clock_throttle_out_lines=( $gpu_clock_throttle_query_out )
   IFS=$' \t\n'
}

collect_gpu_clock_throttle_data
for ((i=0; i<${#gpu_clock_throttle_out_lines[*]}; i++))
do
  IFS=$', '
  gpu_clock_throttle_out_line=( ${gpu_clock_throttle_out_lines[$i]} )
  IFS=$' \t\n'
  if [[ ${gpu_clock_throttle_out_line[0]} != $GPU_CLOCKS_THROTTLE_REASON_GPU_IDLE && ${gpu_clock_throttle_out_line[0]} != $GPU_CLOCKS_THROTTLE_REASON_NONE && ${gpu_clock_throttle_out_line[0]} != $GPU_CLOCKS_THROTTLE_REASON_SW_POWER_CAP ]]; then
     echo "Warning: GPU $i throttled, reason=${gpu_clock_throttle_out_line[0]}"
     exit 0
  fi
done
echo "No GPU throttling detected"
exit 0 