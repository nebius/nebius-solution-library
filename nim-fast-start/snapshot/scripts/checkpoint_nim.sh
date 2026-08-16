#!/usr/bin/env bash
# Generic sm90 NIM checkpoint: validate inference -> harvest JIT -> criu dump.
# Usage: sm90_ckpt.sh <nim> <app-label> <agent-pod>
set -uo pipefail
NIM="$1"; APP="$2"; AGENT="$3"
export H100KC=~/.kube/archvteams-2407-baselines.yaml
NS=nim-fast-start
POD=$(kubectl --kubeconfig $H100KC get pod -n $NS -l app=$APP -o jsonpath='{.items[0].metadata.name}')
echo "NIM=$NIM POD=$POD AGENT=$AGENT"

echo "=== A: functional inference ==="
kubectl --kubeconfig $H100KC exec -n $NS "$POD" -- bash -c '
set -e
NIM='"$NIM"'
curl -sf https://files.rcsb.org/download/1UBQ.pdb -o /tmp/1ubq.pdb
if [ "$NIM" = "rfdiffusion" ]; then
  python3 - <<PY
import json
pdb = open("/tmp/1ubq.pdb").read()
json.dump({"input_pdb":pdb,"contigs":"A20-60/0 20-30","diffusion_steps":15}, open("/tmp/dd.json","w"))
PY
  URL=http://127.0.0.1:8000/biology/ipd/rfdiffusion/generate
elif [ "$NIM" = "diffdock" ]; then
  python3 - <<PY
import json
pdb = open("/tmp/1ubq.pdb").read()
json.dump({"ligand":"CC(=O)Oc1ccccc1C(=O)O","ligand_file_type":"txt","protein":pdb,"num_poses":1,"time_divisions":20,"steps":18}, open("/tmp/dd.json","w"))
PY
  URL=http://127.0.0.1:8000/molecular-docking/diffdock/generate
fi
for i in 1 2; do
  T0=$(date +%s%3N)
  CODE=$(curl -sS --max-time 600 -o /tmp/inf$i.json -w "%{http_code}" -H "Content-Type: application/json" -X POST "$URL" --data @/tmp/dd.json 2>/dev/null || true)
  T1=$(date +%s%3N)
  BYTES=$(stat -c %s /tmp/inf$i.json 2>/dev/null || echo 0)
  echo "INFER_$i: http=$CODE bytes=$BYTES ms=$((T1-T0))"
  [ "$CODE" != "200" ] && head -c 200 /tmp/inf$i.json && exit 90
  [ "$BYTES" -le 200 ] && exit 90
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
CUDA_PID=""
for p in $FPIDS; do
  ST=$(/usr/local/bin/cuda-checkpoint --get-state --pid $p 2>/dev/null || true)
  [ "$ST" = "running" ] && CUDA_PID=$p && break
done
echo "ROOT=$ROOT CUDA_PID=${CUDA_PID:-none} (procs:$(echo $FPIDS | wc -w))"
[ -z "$CUDA_PID" ] && echo NO_CUDA_PID && exit 93
T0=$(date +%s%3N)
/usr/local/bin/cuda-checkpoint --action lock --pid $CUDA_PID --timeout 60000 || { echo LOCK_FAIL; exit 94; }
/usr/local/bin/cuda-checkpoint --action checkpoint --pid $CUDA_PID || { /usr/local/bin/cuda-checkpoint --action unlock --pid $CUDA_PID; echo CKPT_FAIL; exit 95; }
T1=$(date +%s%3N)
echo "cuda lock+checkpoint: $((T1-T0))ms"
SKIP_ARGS=""
while IFS= read -r mnt; do SKIP_ARGS="$SKIP_ARGS --skip-mnt $mnt"; done < <(awk "{dev=\$3; mp=\$5} dev==\"253:1\"{print mp} dev==\"0:26\"{print mp} dev==\"0:392\"{print mp}" /proc/$CUDA_PID/mountinfo)
rm -rf /snapshots/$NIM/criu42-v1
mkdir -p /snapshots/$NIM/criu42-v1
T2=$(date +%s%3N)
/opt/criu/criu-patched dump -t $ROOT -D /snapshots/$NIM/criu42-v1 -o criu.log -R \
  --tcp-established --ext-unix-sk --shell-job --link-remap --ghost-limit 104857600 $SKIP_ARGS
CRIU_EXIT=$?
T3=$(date +%s%3N)
echo "criu dump: $((T3-T2))ms exit=$CRIU_EXIT"
/usr/local/bin/cuda-checkpoint --action restore --pid $CUDA_PID
/usr/local/bin/cuda-checkpoint --action unlock --pid $CUDA_PID
echo "donor cuda state: $(/usr/local/bin/cuda-checkpoint --get-state --pid $CUDA_PID)"
if [ $CRIU_EXIT -ne 0 ]; then tail -8 /snapshots/$NIM/criu42-v1/criu.log; exit 96; fi
du -sb /snapshots/$NIM/criu42-v1 | cut -f1
'
RC=$?
[ $RC -ne 0 ] && echo "DUMP_FAILED rc=$RC" && exit $RC

echo ""
echo "=== C: donor post-dump inference ==="
sleep 3
kubectl --kubeconfig $H100KC exec -n $NS "$POD" -- bash -c '
NIM='"$NIM"'
if [ "$NIM" = "diffdock" ]; then URL=http://127.0.0.1:8000/molecular-docking/diffdock/generate; else URL=http://127.0.0.1:8000/biology/ipd/rfdiffusion/generate; fi
CODE=$(curl -sS --max-time 600 -o /tmp/post.json -w "%{http_code}" -H "Content-Type: application/json" -X POST "$URL" --data @/tmp/dd.json 2>/dev/null || true)
echo "POSTDUMP: http=$CODE bytes=$(stat -c %s /tmp/post.json 2>/dev/null || echo 0)"
'
echo "${NIM}_DUMP_COMPLETE"
