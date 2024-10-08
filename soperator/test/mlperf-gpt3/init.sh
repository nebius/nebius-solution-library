#!/bin/bash

set -e

usage() { echo "usage: ${0} [-g <cluster_wide_gpu_count>] [-h]" >&2; exit 1; }

while getopts g:u:k:a:p:n:h flag
do
    case "${flag}" in
        g) GPUS=${OPTARG};;
        h) usage;;
        *) usage;;
    esac
done

if [ -z "${GPUS}" ]; then
    GPUS=64
fi

h1() { echo -e "$(tput setab 12)$(tput setaf 0)$(tput bold) ${1} $(tput sgr0)"; }
h2() { echo -e "$(tput setab 14)$(tput setaf 0) ${1} $(tput sgr0)"; }
hdone() { echo -e "$(tput setab 10)$(tput setaf 0) Done $(tput sgr0)"; }

ROOT_DIR="${1:-/gpt3}"
DATA_DIR="${ROOT_DIR}/dataset"
CKPT_DIR="${ROOT_DIR}/checkpoint"
TRAIN_DIR="${ROOT_DIR}/training"
LOG_DIR="${ROOT_DIR}/logs"

# region Dirs

h1 'Creating directories...'

mkdir -p "${DATA_DIR}"
mkdir -p "${CKPT_DIR}"
mkdir -p "${LOG_DIR}"

hdone

# endregion Dirs

# region MLCommons training repo

h1 'Preparing MLCommons/training repository...'

h2 'Cloning repository...'
git clone --depth 1 https://github.com/mlcommons/training "${TRAIN_DIR}"
pushd "${TRAIN_DIR}"
  git fetch --depth 1 origin 00f04c57d589721aabce4618922780d29f73cf4e
  git checkout 00f04c57d589721aabce4618922780d29f73cf4e
popd

h2 'Patching...'
cp patches/megatron.diff "${TRAIN_DIR}/large_language_model/megatron-lm/"
pushd "${TRAIN_DIR}/large_language_model/megatron-lm"
  patch -i megatron.diff
popd

h2 'Cleaning up...'
pushd "${TRAIN_DIR}"
  rm -rf \
    .github \
    benchmark_readme_template.md \
    image_classification \
    image_segmentation \
    language_model \
    large_language_model/paxml \
    object_detection\
    recommendation\
    recommendation_v2\
    reference_results.md\
    retired_benchmarks\
    rnn_speech_recognition\
    single_stage_detector\
    stable_diffusion
popd

hdone

# endregion MLCommons training repo

# region Rclone

h1 'Configuring Rclone...'

h2 'Installing...'
curl https://rclone.org/install.sh | bash

h2 'Creating config...'
rclone \
  config \
    create \
      mlc-training \
      s3 \
        provider=Cloudflare \
        access_key_id=76ea42eadb867e854061a1806220ee1e \
        secret_access_key=a53625c4d45e3ca8ac0df8a353ea3a41ffc3292aa25259addd8b7dc5a6ce2936 \
        endpoint=https://c2686074cb2caf5cbaf6d134bdba8b47.r2.cloudflarestorage.com

hdone

# endregion Rclone

# region Dataset

h1 'Preparing dataset...'

pushd "${DATA_DIR}"
  h2 'Downloading BPE related files...'
  mkdir "bpe"
  wget -O bpe/vocab.json https://huggingface.co/gpt2/resolve/main/vocab.json
  wget -O bpe/merges.txt https://huggingface.co/gpt2/resolve/main/merges.txt

  h2 'Downloading C4:en dataset archive...'
  rclone \
    copy \
      -P \
      mlc-training:mlcommons-training-wg-public/gpt3/megatron-lm/dataset_c4_spm.tar \
      ./

  h2 'Unpacking C4:en dataset archive...'
  tar --blocking-factor=8192 -xvf dataset_c4_spm.tar

  h2 'Cleaning up...'
  rm -rf \
    dataset_c4_spm.tar \
    spm
popd

hdone

# endregion Dataset

# region Checkpoint

# TODO: Describe checkpoint downloading process

# endregion Checkpoint

# region Run script

h1 'Generating run script...'

cat > "${ROOT_DIR}/run.sh" << EOF
export MASTER_ADDR='worker-0'
export WORLD_SIZE="${GPUS}"

export COM_DIR="${DATA_DIR}/preprocessed_c4_spm"
export BPE_DIR="${DATA_DIR}/bpe"

export EXTERNAL_MODEL_CHECKPOINT_DIR="${CKPT_DIR}/bf16/ckpt4000"
export USE_BF16='true'

export LOG_DIR="${LOG_DIR}"

export CONT='cr.nemax.nebius.cloud/crn02m09qcuniqo1fh1s/llm-gpt'

pushd "${TRAIN_DIR}/large_language_model/megatron-lm"
  sbatch run_gpt3.sh "\${LOG_DIR}" "\${BPE_DIR}" "\${CONT}"
popd
EOF

chmod +x "${ROOT_DIR}/run.sh"

hdone

# endregion Run script

# region Finalizing

h1 'Finalizing...'

h2 'Setting rights...'
chown -R 0:0 "${ROOT_DIR}"

hdone

# endregion Finalizing
