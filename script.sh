#!/usr/bin/env bash
set -euo pipefail

MOUNTPOINT="${1:-/mnt/local-nvme}"
FILESYSTEM_TYPE="ext4"
MD_DEV="/dev/md0"
case "${FILESYSTEM_TYPE}" in
  ext4)
    MOUNT_OPTS="noatime,nodiratime,lazytime,commit=60"
    MKFS_CMD=(mkfs.ext4 -F -m 0)
    ;;
  xfs)
    MOUNT_OPTS="noatime,nodiratime,logbufs=8,inode64"
    MKFS_CMD=(mkfs.xfs -f)
    ;;
  *)
    echo "Unsupported filesystem type: ${FILESYSTEM_TYPE}"
    exit 1
    ;;
esac

echo "Detecting NVMe disks..."
nvme list

mapfile -t NVME_DISKS < <(
  nvme list | awk 'NR>2 && $1 ~ /^\/dev\/nvme[0-9]+n[0-9]+$/ { print $1 }' | sort -V | uniq
)

ROOT_SOURCE="$(findmnt -n -o SOURCE / || true)"
ROOT_PKNAME="$(lsblk -no PKNAME "${ROOT_SOURCE}" 2>/dev/null || true)"
if [[ -n "${ROOT_PKNAME}" ]]; then
  ROOT_DISK="/dev/${ROOT_PKNAME}"
  FILTERED=()
  for d in "${NVME_DISKS[@]}"; do
    if [[ "${d}" != "${ROOT_DISK}" ]]; then
      FILTERED+=("${d}")
    fi
  done
  NVME_DISKS=("${FILTERED[@]}")
fi

DISK_COUNT="${#NVME_DISKS[@]}"
if (( DISK_COUNT < 2 || DISK_COUNT > 8 )); then
  echo "Expected 2..8 NVMe disks for RAID0, found ${DISK_COUNT}: ${NVME_DISKS[*]}"
  exit 1
fi

for d in "${NVME_DISKS[@]}"; do
  [[ -b "${d}" ]] || { echo "Block device not found: ${d}"; exit 1; }
done

echo "Using ${DISK_COUNT} NVMe disk(s): ${NVME_DISKS[*]}"

for d in "${NVME_DISKS[@]}"; do
  DISK_BASENAME="$(basename "${d}")"
  SCHEDULER_PATH="/sys/block/${DISK_BASENAME}/queue/scheduler"
  if [[ -w "${SCHEDULER_PATH}" ]]; then
    echo none | tee "${SCHEDULER_PATH}" >/dev/null
  else
    echo "Skipping scheduler update for ${d}: ${SCHEDULER_PATH} is not writable"
  fi
done

if [[ -e "${MD_DEV}" ]]; then
  mdadm --stop "${MD_DEV}" || true
fi

for d in "${NVME_DISKS[@]}"; do
  echo "Preparing ${d}"

  if lsblk -nr -o MOUNTPOINT "${d}" | grep -q .; then
    echo "Refusing to wipe mounted device: ${d}"
    lsblk "${d}"
    exit 1
  fi

  mdadm --zero-superblock --force "${d}" 2>/dev/null || true
  wipefs --all --force "${d}"
  blockdev --rereadpt "${d}" 2>/dev/null || true
done

udevadm settle

mdadm --create "${MD_DEV}" \
  --level=0 \
  --raid-devices="${DISK_COUNT}" \
  --run \
  --force \
  "${NVME_DISKS[@]}"

udevadm settle

"${MKFS_CMD[@]}" "${MD_DEV}"

mkdir -p "${MOUNTPOINT}"
mount -o "${MOUNT_OPTS}" "${MD_DEV}" "${MOUNTPOINT}"

UUID="$(blkid -s UUID -o value "${MD_DEV}")"
grep -q "${UUID}" /etc/fstab || echo "UUID=${UUID} ${MOUNTPOINT} ${FILESYSTEM_TYPE} ${MOUNT_OPTS},nofail 0 2" >> /etc/fstab

if [[ -d /etc/mdadm ]]; then
  mdadm --detail --scan > /etc/mdadm/mdadm.conf
fi

echo "Done."
echo "RAID device: ${MD_DEV}"
echo "Mounted at : ${MOUNTPOINT}"
df -h "${MOUNTPOINT}"
