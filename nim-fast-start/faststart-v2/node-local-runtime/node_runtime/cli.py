"""Concrete node-local CLI path used by the VM agent (fake OCI is test-only)."""
from __future__ import annotations
import argparse, hashlib, hmac, json, os
from pathlib import Path
from typing import Any

def _canon(x: Any) -> bytes: return json.dumps(x, sort_keys=True, separators=(",", ":")).encode()
def _mac(key: bytes, x: Any) -> str: return hmac.new(key, _canon(x), hashlib.sha256).hexdigest()
class CLIReject(RuntimeError): pass

class OCIBackend:
    """Adapter boundary for containerd/runc; fake mode emits measured-shaped receipts."""
    def __init__(self, key: bytes, fake: bool = False): self.key,self.fake,self.started=key,fake,False
    def drain(self): return {"schema":"drain/v4","complete":True,"authority":"oci-adapter"}
    def gpu_zero(self): return {"schema":"gpu-zero/v4","foreign_processes":0,"memory_zero":True,"authority":"oci-adapter","gpu_uuid":"fake-gpu"}
    def launch(self, checkpoint: bytes): self.started=True
    def infer(self, payload: bytes): return json.dumps({"oracle":"pinned-semantic-oracle-v1","input_sha256":hashlib.sha256(payload).hexdigest()},sort_keys=True).encode()
    def validate(self,payload,response):
        x=json.loads(response); return x.get("oracle")=="pinned-semantic-oracle-v1" and x.get("input_sha256")==hashlib.sha256(payload).hexdigest()
    def cleanup(self, ids, key):
        body={"schema":"cleanup/v4","authority":"oci-adapter","resources":[{"id":i,"absent":True,"status":"NOT_FOUND"} for i in ids]}
        return {**body,"signature":_mac(key,body)}

def run(spec: dict[str,Any]) -> dict[str,Any]:
    key=bytes.fromhex(spec["key_hex"]); state=spec["trusted_state"]; now=int(spec["now_ns"])
    requests=spec["requests"]
    if len(requests)!=2 or requests[0]["payload"]==requests[1]["payload"]: raise CLIReject("two distinct requests required")
    accepted=[]
    for e in spec["external_ledger"]:
        body={k:v for k,v in e.items() if k!="signature"}
        if e.get("schema")!="external-t0/v4" or e.get("recorder")!="trusted-client-recorder" or e.get("accepted_ns",0)>now or now-e["accepted_ns"]>5_000_000_000 or not hmac.compare_digest(e.get("signature",""),_mac(key,body)): raise CLIReject("external ledger T0 rejected")
        accepted.append(e["attempt_id"])
    if set(accepted)!={r["attempt_id"] for r in requests}: raise CLIReject("ledger/request mismatch")
    used=set(spec.get("used_nonces",[])); commands=spec["commands"]
    for c,r in zip(commands,requests):
        body={k:v for k,v in c.items() if k!="signature"}
        if c["attempt_id"]!=r["attempt_id"] or c["nonce"] in used or c["deadline_ns"]<now or c["input_sha256"]!=hashlib.sha256(r["payload"].encode()).hexdigest() or any(c[k]!=state[k] for k in ("instance_id","boot_id","lease_id","owner","environment")) or not hmac.compare_digest(c["signature"],_mac(key,body)): raise CLIReject("admission rejected")
        used.add(c["nonce"])
    backend=OCIBackend(key, fake=spec.get("fake_oci",False)); lock=Path(spec["lock"]); lock.parent.mkdir(parents=True,exist_ok=True)
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.close(fd)
    except FileExistsError: raise CLIReject("exclusive lease denied")
    try:
        if spec.get("storage_observation",{}).get("storage")!="network-ssd" or spec["storage_observation"].get("observed") is not True: raise CLIReject("Network SSD readiness not observed")
        if backend.drain().get("complete") is not True or backend.gpu_zero().get("memory_zero") is not True: raise CLIReject("authority receipt missing")
        checkpoint=bytes.fromhex(spec["checkpoint_hex"])
        if hashlib.sha256(checkpoint).hexdigest()!=spec["checkpoint_sha256"] or spec["checkpoint_environment"]!=state["environment"]: raise CLIReject("checkpoint binding")
        backend.launch(checkpoint); results=[]
        for r in requests:
            response=backend.infer(r["payload"].encode());
            if not backend.validate(r["payload"].encode(),response): raise CLIReject("semantic oracle rejected response")
            results.append(json.loads(response))
        receipt=backend.cleanup(spec["resource_ids"],key)
        if not spec["resource_ids"] or receipt["schema"]!="cleanup/v4" or not hmac.compare_digest(receipt["signature"],_mac(key,{k:v for k,v in receipt.items() if k!="signature"})): raise CLIReject("cleanup authority")
        return {"results":results,"storage":"network-ssd-control","cleanup":receipt}
    finally:
        if lock.exists(): lock.unlink()

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--spec",required=True); p.add_argument("--output",required=True); a=p.parse_args(argv)
    try: result=run(json.loads(Path(a.spec).read_text())); Path(a.output).write_text(json.dumps(result,sort_keys=True)); return 0
    except Exception as exc: print(f"REJECT: {exc}"); return 2
if __name__=="__main__": raise SystemExit(main())
