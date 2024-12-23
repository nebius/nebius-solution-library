set -x
PIPE_DIR=$(dirname $CUDA_COREDUMP_PIPE)
echo "$0: dumping GPU core to ${CUDA_COREDUMP_FILE} by triggering pipes from ${PIPE_DIR}"
for corepipe in ${PIPE_DIR}/*; do
  echo 1 >> $corepipe &
done
echo "Dumping cores done on host $(hostname)"
