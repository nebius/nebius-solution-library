set -eux
: "${HANG_MONITOR_TIMEOUT:?HANG_MONITOR_TIMEOUT not set}"
: "${HANG_MONITOR_EXEC_CMD:?HANG_MONITOR_EXEC_CMD not set}"
: "${SLURM_JOBID:?SLURM_JOBID not set}"
timeleft_to_seconds() {
  timeleft=$1
  timeleft_arr=(`echo $timeleft | tr ':-' ' '`)
  seconds_left=${timeleft_arr[2]}
  
  if [ "${timeleft_arr[1]}" != "" ]; then
    seconds_left=$(( seconds_left + timeleft_arr[1] * 60 ))
  fi

  if [ "${timeleft_arr[0]}" != "" ]; then
    seconds_left=$(( seconds_left + timeleft_arr[0] * 3600 ))
  fi

  echo $seconds_left
}
hang_monitor() {
  echo "Launching hang monitor"
  sleep 60
  timeleft=`squeue -j ${SLURM_JOBID} --noheader --format=%L`
  sleep_duration=$(( $(timeleft_to_seconds $timeleft) - 60 * HANG_MONITOR_TIMEOUT ))
  if [ -z "$sleep_duration" ]; then
    echo "Invalid sleep duration. Hang monitor won't be launched"
    return
  fi
  if [ "$sleep_duration" -gt 0 ]; then
    sleep $sleep_duration
  fi
  echo "Launching tracebacks script for timeout ${HANG_MONITOR_TIMEOUT}"
  bash -c "$HANG_MONITOR_EXEC_CMD"
  echo "Tracebacks script done"
}
