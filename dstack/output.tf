output "dstack_password" {
  sensitive = true
  value     = random_password.dstack_app.result
}
