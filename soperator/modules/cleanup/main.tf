resource "terraform_data" "disk_cleanup" {
  provisioner "local-exec" {
    when        = destroy
    interpreter = ["/bin/bash", "-c"]
    environment = {
      "PARENT_ID": var.iam_project_id,
    }
    command     = "scripts/disk_cleanup.sh"
  }
}
