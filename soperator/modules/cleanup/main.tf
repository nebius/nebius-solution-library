
resource "terraform_data" "disk_cleanup" {
  input = {
    parallelism = tostring(var.parallelism)
  }

  triggers_replace = {
    parent_id = var.iam_project_id
  }

  provisioner "local-exec" {
    when        = destroy
    interpreter = ["/bin/bash", "-c"]

    environment = {
      "PARENT_ID" : self.triggers_replace.parent_id,
      "MAX_DELETE_JOBS" : try(self.output.parallelism, "10"),
    }
    command = "${path.module}/scripts/disk_cleanup.sh"
  }
}
