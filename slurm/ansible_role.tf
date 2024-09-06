data "archive_file" "ansible_role" {
  type        = "zip"
  output_path = "files/ansible_role.zip"
  source_dir  = "files/ansible"
}
