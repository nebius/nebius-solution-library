locals {
  service_account_name = join(
    "-",
    [
      "o11y",
      "slurm",
      var.company_name,
      var.region,
      var.o11y_iam_tenant_id,
      var.o11y_iam_project_id,
    ]
  )
}