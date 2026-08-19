from __future__ import annotations
import hashlib, hmac, json, os
from pathlib import Path
from typing import Any, Protocol

class Reject(RuntimeError): pass
def canon(x: Any) -> bytes: return json.dumps(x, sort_keys=True, separators=(",", ":")).encode()
def sha(x: Any) -> str: return hashlib.sha256(canon(x)).hexdigest()
def mac(k: bytes, x: Any) -> str: return hmac.new(k, canon(x), hashlib.sha256).hexdigest()

class Backend(Protocol):
    def drain(self) -> dict[str, Any]: ...
    def gpu_zero(self) -> dict[str, Any]: ...
    def launch(self, checkpoint: bytes | None) -> None: ...
    def infer(self, payload: bytes) -> bytes: ...
    def validate(self, payload: bytes, response: bytes) -> bool: ...
    def cleanup(self, ids: list[str]) -> dict[str, Any]: ...

class Supervisor:
    """Production entry point: all gates execute inside this request path."""
    def __init__(self, root: Path, *, key: bytes, state: dict[str, str], backend: Backend) -> None:
        self.root, self.key, self.state, self.backend = root, key, state, backend
        self.root.mkdir(parents=True, exist_ok=True)
        self.nonces = self.root / "nonces.json"
        self.accepted: dict[str, dict[str, Any]] = {}
        self._load_nonces()
        self.lease = self.root / "exclusive.lock"

    def _load_nonces(self) -> None:
        self.used = set(json.loads(self.nonces.read_text())) if self.nonces.exists() else set()
    def _save_nonce(self, n: str) -> None:
        self.used.add(n); tmp=self.nonces.with_suffix(".tmp"); tmp.write_text(json.dumps(sorted(self.used))); os.replace(tmp, self.nonces)

    def ingest_t0(self, event: dict[str, Any], *, now_ns: int) -> None:
        req={"schema","attempt_id","accepted_ns","payload_sha256","model_id","model_version","recorder","signature"}
        if set(event)!=req or event["schema"]!="external-t0/v3" or event["recorder"]!="trusted-client-recorder": raise Reject("T0 contract")
        if event["accepted_ns"]>now_ns or now_ns-event["accepted_ns"]>5_000_000_000: raise Reject("late T0")
        body={k:v for k,v in event.items() if k!="signature"}
        if not hmac.compare_digest(event["signature"],mac(self.key,body)): raise Reject("T0 signature")
        if event["attempt_id"] in self.accepted: raise Reject("duplicate T0")
        self.accepted[event["attempt_id"]]=event

    def run(self, *, commands: list[dict[str,Any]], payloads: list[bytes], checkpoint: bytes, checkpoint_sha256: str, checkpoint_env: str, resource_ids: list[str], now_ns: int) -> list[bool]:
        if len(commands)!=2 or len(payloads)!=2 or payloads[0]==payloads[1]: raise Reject("two distinct requests required")
        attempts=[c["attempt_id"] for c in commands]
        if set(attempts)!=set(self.accepted): raise Reject("only externally accepted attempts allowed")
        for c,p in zip(commands,payloads):
            required={"schema","attempt_id","nonce","deadline_ns","instance_id","boot_id","lease_id","owner","environment","input_sha256","signature"}
            if set(c)!=required or c["schema"]!="admission/v3" or c["input_sha256"]!=hashlib.sha256(p).hexdigest(): raise Reject("admission/input")
            if c["nonce"] in self.used or c["deadline_ns"]<now_ns: raise Reject("replay/deadline")
            for k in ("instance_id","boot_id","lease_id","owner","environment"):
                if c[k]!=self.state[k]: raise Reject("trusted state")
            body={k:v for k,v in c.items() if k!="signature"}
            if not hmac.compare_digest(c["signature"],mac(self.key,body)): raise Reject("admission signature")
            self._save_nonce(c["nonce"])
        try:
            fd=os.open(self.lease,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.write(fd,b"owned"); os.close(fd)
        except FileExistsError: raise Reject("lease denied")
        try:
            drain=self.backend.drain()
            if drain.get("schema")!="drain/v3" or drain.get("complete") is not True: raise Reject("drain receipt")
            gpu=self.backend.gpu_zero()
            if gpu.get("schema")!="gpu-zero/v3" or gpu.get("foreign_processes")!=0 or gpu.get("memory_zero") is not True: raise Reject("GPU receipt")
            if hashlib.sha256(checkpoint).hexdigest()!=checkpoint_sha256 or checkpoint_env!=self.state["environment"]: raise Reject("checkpoint binding")
            self.backend.launch(checkpoint)
            out=[]
            for p in payloads:
                r=self.backend.infer(p)
                if not self.backend.validate(p,r): raise Reject("semantic validation")
                out.append(True)
            receipt=self.backend.cleanup(resource_ids)
            body={k:v for k,v in receipt.items() if k!="signature"}
            if receipt.get("schema")!="cleanup/v3" or not resource_ids or not hmac.compare_digest(receipt.get("signature",""),mac(self.key,body)): raise Reject("cleanup signature")
            if {x.get("id") for x in receipt.get("resources",[])}!=set(resource_ids) or any(x.get("absent") is not True for x in receipt["resources"]): raise Reject("cleanup absence")
            return out
        finally:
            if self.lease.exists(): self.lease.unlink()
