#!/usr/bin/env bash
# Generic sm90 NIM checkpoint: validate inference -> harvest JIT -> criu dump.
# Usage: sm90_ckpt.sh <nim> <app-label> <agent-pod>
set -uo pipefail
NIM="$1"; APP="$2"; AGENT="$3"
export H100KC="${KC:-$HOME/.kube/archvteams-2407-baselines.yaml}"
NS=nim-fast-start
POD=$(kubectl --kubeconfig $H100KC get pod -n $NS -l app=$APP --field-selector status.phase=Running -o jsonpath='{.items[0].metadata.name}')
echo "NIM=$NIM POD=$POD AGENT=$AGENT"

echo "=== A: functional inference ==="
kubectl --kubeconfig $H100KC exec -n $NS "$POD" -- bash -c '
set -e
NIM='"$NIM"'
curl -sf https://files.rcsb.org/download/1UBQ.pdb -o /tmp/1ubq.pdb || true
python3 - "$NIM" <<PY
import json, sys
nim = sys.argv[1]
P20 = "ACDEFGHIKLMNPQRSTVWY"
pdb = open("/tmp/1ubq.pdb").read() if nim in ("rfdiffusion","diffdock","proteinmpnn") else None
payloads = {
  "rfdiffusion": ({"input_pdb":pdb,"contigs":"A20-60/0 20-30","diffusion_steps":15},
                  "/biology/ipd/rfdiffusion/generate"),
  "diffdock":    ({"ligand":"CC(=O)Oc1ccccc1C(=O)O","ligand_file_type":"txt","protein":pdb,
                   "num_poses":1,"time_divisions":20,"steps":18},
                  "/molecular-docking/diffdock/generate"),
  "genmol":      ({"smiles":"[*{20-30}]","num_molecules":1,"unique":False}, "/generate"),
  "molmim":      ({"smi":"c1ccccc1","algorithm":"none","num_molecules":1}, "/generate"),
  "proteinmpnn": ({"input_pdb":pdb,"num_seq_per_target":1,"random_seed":2370},
                  "/biology/ipd/proteinmpnn/predict"),
  "boltz2":      ({"polymers":[{"molecule_type":"protein","sequence":P20,"id":"A"}],
                   "recycling_steps":1,"sampling_steps":10,"diffusion_samples":1,
                   "output_format":"mmcif"}, "/biology/mit/boltz2/predict"),
  "openfold3":   ({"request_id":"ckpt-openfold3","inputs":[{"input_id":"ckpt-openfold3",
                   "output_format":"cif","molecules":[{"type":"protein","id":"A",
                   "sequence":P20,"diffusion_samples":1,
                   "msa":{"main":{"a3m":{"alignment":">query\n"+P20,"format":"a3m"}}}}]}]},
                  "/biology/openfold/openfold3/predict"),
}
body, path = payloads[nim]
json.dump(body, open("/tmp/dd.json","w"))
open("/tmp/dd.url","w").write("http://127.0.0.1:8000"+path)
PY
URL=$(cat /tmp/dd.url)
for i in 1 2; do
  T0=$(date +%s%3N)
  CODE=$(curl -sS --max-time 600 -o /tmp/inf$i.json -w "%{http_code}" -H "Content-Type: application/json" -X POST "$URL" --data @/tmp/dd.json 2>/dev/null || true)
  T1=$(date +%s%3N)
  BYTES=$(stat -c %s /tmp/inf$i.json 2>/dev/null || echo 0)
  echo "INFER_$i: http=$CODE bytes=$BYTES ms=$((T1-T0))"
  [ "$CODE" != "200" ] && head -c 200 /tmp/inf$i.json && exit 90
  [ "$BYTES" -le 50 ] && exit 90
done
echo "=== harvest JIT/caches ==="
cd /
LIST=""
for d in root/.cache/tvm-ffi tmp/root/bionemo_kernel_cache root/.triton root/.cache/torch_extensions root/.nv/ComputeCache; do
  [ -e "/$d" ] && LIST="$LIST $d"
done
echo "harvest:$LIST"
if [ -n "$LIST" ]; then tar cf /home/user/.cache/nim/jit-$NIM-v1.tar -C / $LIST; else tar cf /home/user/.cache/nim/jit-$NIM-v1.tar --files-from /dev/null; fi
ls -la /home/user/.cache/nim/jit-$NIM-v1.tar
' || { echo "INFERENCE_OR_HARVEST_FAILED"; exit 90; }

echo ""
echo "=== B: dump via agent ==="
PODUID=$(kubectl --kubeconfig $H100KC get pod -n $NS "$POD" -o jsonpath='{.metadata.uid}')
kubectl --kubeconfig $H100KC exec -n $NS "$AGENT" -c agent -- bash -c '
set -uo pipefail
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
# CRIU shells out to these during dump; stub them (network state is discarded
# at restore anyway: --empty-ns net + --tcp-close).
for c in ip iptables-restore ip6tables-restore iptables-save ip6tables-save; do
  [ -x "/usr/local/bin/$c" ] || printf "#!/bin/sh\nexit 0\n" > "/usr/local/bin/$c" && chmod 755 "/usr/local/bin/$c"
done
export PATH=/usr/local/bin:$PATH
NIM='"$NIM"'
PODUID='"$PODUID"'
UID_UND=${PODUID//-/_}
# All pids of the pod via its cgroup (authoritative, env-independent)
PIDS=$(cat $(find /sys/fs/cgroup -path "*${UID_UND}*" -name cgroup.procs 2>/dev/null) 2>/dev/null | sort -un)
[ -z "$PIDS" ] && echo NO_PIDS && exit 92
# Drop the pause container process
FPIDS=""
for p in $PIDS; do
  COMM=$(cat /proc/$p/comm 2>/dev/null || true)
  [ "$COMM" = "pause" ] && continue
  FPIDS="$FPIDS $p"
done
ROOT=$(echo $FPIDS | tr " " "\n" | sort -n | head -1)
# Multi-worker NIMs (e.g. boltz2 = 4 uvicorn workers) can hold MULTIPLE CUDA
# contexts. Every proc with a live CUDA context must be locked+checkpointed, or
# an un-checkpointed device VMA fails the dump ("handle_device_vma plugin failed").
CUDA_PIDS=""
for p in $FPIDS; do
  ST=$(/usr/local/bin/cuda-checkpoint --get-state --pid $p 2>/dev/null || true)
  [ "$ST" = "running" ] && CUDA_PIDS="$CUDA_PIDS $p"
done
CUDA_PID=$(echo $CUDA_PIDS | awk "{print \$1}")
echo "ROOT=$ROOT CUDA_PIDS=[${CUDA_PIDS# }] (procs:$(echo $FPIDS | wc -w))"
[ -z "$CUDA_PID" ] && echo NO_CUDA_PID && exit 93
T0=$(date +%s%3N)
LOCKED=""
for cp in $CUDA_PIDS; do
  /usr/local/bin/cuda-checkpoint --action lock --pid $cp --timeout 60000 || { echo "LOCK_FAIL $cp"; for u in $LOCKED; do /usr/local/bin/cuda-checkpoint --action unlock --pid $u; done; exit 94; }
  LOCKED="$LOCKED $cp"
done
for cp in $CUDA_PIDS; do
  /usr/local/bin/cuda-checkpoint --action checkpoint --pid $cp || { echo "CKPT_FAIL $cp"; for u in $CUDA_PIDS; do /usr/local/bin/cuda-checkpoint --action unlock --pid $u; done; exit 95; }
done
T1=$(date +%s%3N)
echo "cuda lock+checkpoint: $((T1-T0))ms"
# io_uring handling: the patched eventpoll.c filters io_uring TFDs from the epoll
# dump WHILE THE FDS ARE OPEN, and pie/parasite.c skips them from the SCM_RIGHTS
# drain. Do NOT inject_close (that closes the FDs the eventpoll filter must
# readlink, breaking the epoll dump). Only close as an explicit last resort.
CLOSED=0
if [ -n "${IO_URING_CLOSE:-}" ]; then
  for p in $FPIDS; do
    for fd in $(ls /proc/$p/fd 2>/dev/null); do
      tgt=$(readlink /proc/$p/fd/$fd 2>/dev/null || true)
      case "$tgt" in
        *"io_uring"*) /opt/criu/inject_close "$p" "$fd" >/dev/null 2>&1 && CLOSED=$((CLOSED+1));;
      esac
    done
  done
  echo "io_uring FDs closed: $CLOSED"
fi
SKIP_ARGS=""
while IFS= read -r mnt; do SKIP_ARGS="$SKIP_ARGS --skip-mnt $mnt"; done < <(awk "{dev=\$3; mp=\$5} dev==\"253:1\"{print mp} dev==\"0:26\"{print mp} dev==\"0:392\"{print mp}" /proc/$CUDA_PID/mountinfo)
rm -rf /snapshots/$NIM/criu42-v1
mkdir -p /snapshots/$NIM/criu42-v1
T2=$(date +%s%3N)
# Hard timeout so a stuck seize (e.g. an io_uring thread that will not quiesce)
# cannot hang forever. NOTE: run ONE dump per agent at a time — two concurrent
# criu dumps on the same agent deadlock on ptrace/seize.
timeout 480 /opt/criu/criu-patched dump -t $ROOT -D /snapshots/$NIM/criu42-v1 -o criu.log -R \
  --tcp-established --ext-unix-sk --shell-job --link-remap --ghost-limit 104857600 \
  --force-irmap $SKIP_ARGS
CRIU_EXIT=$?
[ $CRIU_EXIT -eq 124 ] && echo "CRIU DUMP TIMED OUT (480s)"
T3=$(date +%s%3N)
echo "criu dump: $((T3-T2))ms exit=$CRIU_EXIT"
# restore+unlock EVERY checkpointed CUDA proc (leave-running donor)
for cp in $CUDA_PIDS; do
  /usr/local/bin/cuda-checkpoint --action restore --pid $cp 2>/dev/null
  /usr/local/bin/cuda-checkpoint --action unlock --pid $cp 2>/dev/null
done
echo "donor cuda states: $(for cp in $CUDA_PIDS; do /usr/local/bin/cuda-checkpoint --get-state --pid $cp 2>/dev/null; done | tr "\n" " ")"
if [ $CRIU_EXIT -ne 0 ]; then tail -8 /snapshots/$NIM/criu42-v1/criu.log; exit 96; fi
du -sb /snapshots/$NIM/criu42-v1 | cut -f1
'
RC=$?
[ $RC -ne 0 ] && echo "DUMP_FAILED rc=$RC" && exit $RC

echo ""
echo "=== C: donor post-dump inference (best-effort; io_uring close may break donor) ==="
sleep 3
kubectl --kubeconfig $H100KC exec -n $NS "$POD" -- bash -c '
URL=$(cat /tmp/dd.url)
CODE=$(curl -sS --max-time 600 -o /tmp/post.json -w "%{http_code}" -H "Content-Type: application/json" -X POST "$URL" --data @/tmp/dd.json 2>/dev/null || true)
echo "POSTDUMP: http=$CODE bytes=$(stat -c %s /tmp/post.json 2>/dev/null || echo 0)"
'
echo "${NIM}_DUMP_COMPLETE"
