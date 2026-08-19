from __future__ import annotations
import hashlib,hmac,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from node_runtime.cli import _canon,_mac

class CLIIntegration(unittest.TestCase):
 def test_same_user_cli_runs_fake_oci_and_rejects_regressions(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); key=b"q"*32; now=10**12; state={"instance_id":"i","boot_id":"b","lease_id":"l","owner":"task","environment":"env"}; ps=["alpha","beta"]
   req=[]; ledger=[]; cmds=[]
   for i,p in enumerate(ps):
    a=str(i); req.append({"attempt_id":a,"payload":p}); e={"schema":"external-t0/v4","attempt_id":a,"accepted_ns":now-1,"recorder":"trusted-client-recorder"}; ledger.append({**e,"signature":_mac(key,e)})
    c={"attempt_id":a,"nonce":"n"+a,"deadline_ns":now+100,"instance_id":"i","boot_id":"b","lease_id":"l","owner":"task","environment":"env","input_sha256":hashlib.sha256(p.encode()).hexdigest()}; cmds.append({**c,"signature":_mac(key,c)})
   cp=b"checkpoint"; spec={"key_hex":key.hex(),"trusted_state":state,"now_ns":now,"requests":req,"external_ledger":ledger,"commands":cmds,"used_nonces":[],"fake_oci":True,"lock":str(root/"lock"),"storage_observation":{"storage":"network-ssd","observed":True,"device_id":"disk"},"checkpoint_hex":cp.hex(),"checkpoint_sha256":hashlib.sha256(cp).hexdigest(),"checkpoint_environment":"env","resource_ids":["vm"]}
   sp,out=root/"spec.json",root/"out.json"; sp.write_text(json.dumps(spec)); r=subprocess.run([sys.executable,"-m","node_runtime.cli","--spec",str(sp),"--output",str(out)],cwd=Path(__file__).parents[1],capture_output=True,text=True); self.assertEqual(r.returncode,0,r.stderr); result=json.loads(out.read_text()); self.assertEqual(len(result["results"]),2); self.assertEqual(result["storage"],"network-ssd-control")
   bad=dict(spec); bad["storage_observation"]={"storage":"network-ssd","observed":False}; sp.write_text(json.dumps(bad)); r=subprocess.run([sys.executable,"-m","node_runtime.cli","--spec",str(sp),"--output",str(out)],cwd=Path(__file__).parents[1],capture_output=True,text=True); self.assertEqual(r.returncode,2); self.assertIn("REJECT",r.stdout)
   bad=dict(spec); bad["requests"]=[{"attempt_id":"0","payload":"same"},{"attempt_id":"1","payload":"same"}]; sp.write_text(json.dumps(bad)); r=subprocess.run([sys.executable,"-m","node_runtime.cli","--spec",str(sp),"--output",str(out)],cwd=Path(__file__).parents[1],capture_output=True,text=True); self.assertEqual(r.returncode,2)
   bad=dict(spec); bad["external_ledger"]=[{**ledger[0],"accepted_ns":0}]+[ledger[1]]; sp.write_text(json.dumps(bad)); r=subprocess.run([sys.executable,"-m","node_runtime.cli","--spec",str(sp),"--output",str(out)],cwd=Path(__file__).parents[1],capture_output=True,text=True); self.assertEqual(r.returncode,2)
