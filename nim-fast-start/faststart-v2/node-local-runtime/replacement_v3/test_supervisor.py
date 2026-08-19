from __future__ import annotations
import hashlib, tempfile, unittest
from pathlib import Path
from replacement_v3.supervisor import Supervisor, Reject, mac

class B:
 def __init__(self,key): self.key=key; self.cleaned=0
 def drain(self): return {"schema":"drain/v3","complete":True}
 def gpu_zero(self): return {"schema":"gpu-zero/v3","foreign_processes":0,"memory_zero":True}
 def launch(self,checkpoint): pass
 def infer(self,p): return p[::-1]
 def validate(self,p,r): return r==p[::-1]
 def cleanup(self,ids):
  self.cleaned+=1; x={"schema":"cleanup/v3","resources":[{"id":i,"absent":True} for i in ids]}; return {**x,"signature":mac(self.key,x)}

class E2E(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.key=b"z"*32; self.state={"instance_id":"i","boot_id":"b","lease_id":"l","owner":"task","environment":"env"}; self.b=B(self.key); self.s=Supervisor(self.root,key=self.key,state=self.state,backend=self.b); self.now=10**12
 def t0(self,a,p):
  x={"schema":"external-t0/v3","attempt_id":a,"accepted_ns":self.now-1,"payload_sha256":hashlib.sha256(p).hexdigest(),"model_id":"m","model_version":"1","recorder":"trusted-client-recorder"}; return {**x,"signature":mac(self.key,x)}
 def cmd(self,a,p,n):
  x={"schema":"admission/v3","attempt_id":a,"nonce":n,"deadline_ns":self.now+100,"instance_id":"i","boot_id":"b","lease_id":"l","owner":"task","environment":"env","input_sha256":hashlib.sha256(p).hexdigest()}; return {**x,"signature":mac(self.key,x)}
 def test_integrated_two_request_path(self):
  ps=[b"one",b"two"]
  for i,p in enumerate(ps): self.s.ingest_t0(self.t0(str(i),p),now_ns=self.now)
  self.assertEqual(self.s.run(commands=[self.cmd("0",ps[0],"n0"),self.cmd("1",ps[1],"n1")],payloads=ps,checkpoint=b"c",checkpoint_sha256=hashlib.sha256(b"c").hexdigest(),checkpoint_env="env",resource_ids=["vm"],now_ns=self.now),[True,True])
  self.assertEqual(self.b.cleaned,1)
 def test_regressions_are_rejected(self):
  p=b"same"; self.s.ingest_t0(self.t0("0",p),now_ns=self.now)
  with self.assertRaises(Reject): self.s.run(commands=[self.cmd("0",p,"n0"),self.cmd("0",p,"n1")],payloads=[p,p],checkpoint=b"c",checkpoint_sha256="x",checkpoint_env="bad",resource_ids=[],now_ns=self.now)
 def test_nonce_survives_restart(self):
  p=[b"a",b"b"]
  for i,x in enumerate(p): self.s.ingest_t0(self.t0(str(i),x),now_ns=self.now)
  self.s.run(commands=[self.cmd("0",p[0],"n0"),self.cmd("1",p[1],"n1")],payloads=p,checkpoint=b"c",checkpoint_sha256=hashlib.sha256(b"c").hexdigest(),checkpoint_env="env",resource_ids=["vm"],now_ns=self.now)
  s2=Supervisor(self.root,key=self.key,state=self.state,backend=B(self.key)); s2.accepted=self.s.accepted
  with self.assertRaises(Reject): s2.run(commands=[self.cmd("0",p[0],"n0"),self.cmd("1",p[1],"n2")],payloads=p,checkpoint=b"c",checkpoint_sha256=hashlib.sha256(b"c").hexdigest(),checkpoint_env="env",resource_ids=["vm"],now_ns=self.now)
