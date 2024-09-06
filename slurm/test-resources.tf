resource "null_resource" "master-check-ansible" {
  count = var.test_mode ? 1 : 0
  connection {
    user = "slurm"
    host = trimsuffix(nebius_compute_v1_instance.master.status.network_interfaces[0].public_ip_address.address, "/32")
  }

  provisioner "remote-exec" {
    inline = [
      "until [ -s '/tmp/ansible/ansible.pid' ]; do echo 'Waiting for ansbile process start'; sleep 1; done",
      "until ! ps -p $(cat /tmp/ansible/ansible.pid) > /dev/null; do echo 'Waiting for ansbile process finish'; sleep 1; done",
      "grep -q 'failed=0' /tmp/ansible/ansible.log",
      "grep -q 'unreachable=0' /tmp/ansible/ansible.log",
      "grep -q 'rescued=0' /tmp/ansible/ansible.log",
      "grep -q 'ignored=0' /tmp/ansible/ansible.log",
    ]
  }
}

resource "null_resource" "master-check-slurm" {
  depends_on = [null_resource.master-check-ansible]
  count      = var.test_mode ? 1 : 0
  connection {
    user = "slurm"
    host = trimsuffix(nebius_compute_v1_instance.master.status.network_interfaces[0].public_ip_address.address, "/32")
  }

  provisioner "remote-exec" {
    inline = [
      "sinfo -N",
      "scontrol show nodes --json | jq '.nodes[].state'",
      "! scontrol show nodes --json | jq '.nodes[].state == [\"IDLE\"]' | grep -q false",
      "scontrol show nodes --json | jq '.nodes | length' | grep -q '^${var.cluster_workers_count}$'"
    ]
  }
}

resource "null_resource" "master-run-nccl-tests" {
  depends_on = [null_resource.master-check-slurm]
  count      = var.test_mode ? 1 : 0
  connection {
    user = "slurm"
    host = trimsuffix(nebius_compute_v1_instance.master.status.network_interfaces[0].public_ip_address.address, "/32")
  }

  provisioner "remote-exec" {
    inline = [
      "sbatch -W -N ${var.cluster_workers_count} /home/slurm/nccl.sbatch",
      "! scontrol show job --all --json | jq '.jobs[].job_state == [\"COMPLETED\"]' | grep -q false",
      "bash /home/slurm/nccl.sh ${var.cluster_workers_count}",
      "! scontrol show job --all --json | jq '.jobs[].job_state == [\"COMPLETED\"]' | grep -q false",
    ]
  }
}
