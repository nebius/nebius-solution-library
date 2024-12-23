set -x
: "${TRACEBACKS_ID:=''}"
: "${RESULTS_DIR:=/results/tracebacks}"
: "${ATTEMPT_CUDA_GDB_TRACEBACKS_DUMP:=0}"
: "${CUDA_GDB_BIN:=cuda-gdb}"
RESULTS_PATH=${RESULTS_DIR}/${TRACEBACKS_ID}
echo "$0: dumping tracebacks to ${RESULTS_PATH}"
mkdir -p "${RESULTS_PATH}"
(
  pip install py-spy
  export DEBIAN_FRONTEND=noninteractive;
  apt update
  apt install -y gdb
) &> /dev/null
pids=$(nvidia-smi -q -x | grep pid | sed -e "s/<pid>//g" -e "s/<\/pid>//g" -e "s/^[[:space:]]*//" | sort -u)
echo "Matching processes: $pids"
for pid in ${pids}; do
  if ps -p $pid > /dev/null; then
    slurm_procid=`cat /proc/$pid/environ | tr "\0" "\n" | grep SLURM_PROCID`
    slurm_procid=${slurm_procid:13}
    printf -v slurm_procid "%05d" $slurm_procid
    savefile="$RESULTS_PATH/rank${slurm_procid}_pid${pid}.pyspy"
    hostname &> "$savefile"
    date +'%y%m%d%H%M%S%N' &>> "$savefile"
    py-spy dump --pid $pid &>> "$savefile"
    savefile="$RESULTS_PATH/rank${slurm_procid}_pid${pid}.gdb"
    hostname &> "$savefile"
    date +'%y%m%d%H%M%S%N' &>> "$savefile"
    gdb -p $pid -batch -ex 'thread apply all bt' &>> "$savefile"
  else
    echo "Process $pid doesnt exist anymore"
  fi
done
if [ "${ATTEMPT_CUDA_GDB_TRACEBACKS_DUMP}" -eq 1 ]; then
  sleep 30
  for pid in ${pids}; do
    if ps -p $pid > /dev/null; then
      slurm_procid=`cat /proc/$pid/environ | tr "\0" "\n" | grep SLURM_PROCID`
      slurm_procid=${slurm_procid:13}
      printf -v slurm_procid "%05d" $slurm_procid
      savefile="$RESULTS_PATH/rank${slurm_procid}_pid${pid}.cuda-gdb"
      hostname &> "$savefile"
      date +'%y%m%d%H%M%S%N' &>> "$savefile"
      ${CUDA_GDB_BIN} -batch -ex 'info cuda kernels' -ex 'info cuda devices' -p $pid &>> "$savefile"
    else
      echo "Process $pid doesnt exist anymore"
    fi
  done
fi
echo "Dumping done on host $(hostname)"
