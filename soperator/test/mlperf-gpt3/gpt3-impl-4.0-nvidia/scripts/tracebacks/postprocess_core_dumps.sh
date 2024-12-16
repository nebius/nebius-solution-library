set -x
: "${REMOVE_CUDA_GDB_CORE_DUMP:=1}"
: "${CUDA_GDB_BIN:=cuda-gdb}"
echo "$0: Processing CUDA cores in ${CUDA_COREDUMP_BASEDIR}"
for dump in ${CUDA_COREDUMP_BASEDIR}/*.nvcudmp; do
  savefile="${dump%.nvcudmp}.cuda-gdb"
  ${CUDA_GDB_BIN} -batch -ex "target cudacore $dump" -ex 'info cuda kernels' -ex 'info cuda devices' >> "$savefile"
  if [ $? -eq 0 ] && [ "${REMOVE_CUDA_GDB_CORE_DUMP}" == "1" ] ; then
    echo "Removing core dump $dump"
    rm $dump
  fi
done
echo "Postprocessing CUDA cores done on host $(hostname)"
