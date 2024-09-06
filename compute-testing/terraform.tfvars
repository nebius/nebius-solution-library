parent_id         = "project-e00mkt-sandbox"
subnet_id         = "vpcsubnet-e00ma89v2353yh1z52"
ssh_user_name     = "nebius-user"
public_ssh_key    = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC2ncFI4xJDBm2b/o5YPLMhqTZr62PIpIozWnb8vDdJLzbkDg/cVgZy8QA0yJVYl5dZLh23Zx3ZJ/uFZG+T4XvRjanZhBC3jLttHbPvu22bfF5Gt0CCy0SDhCj4VXjOZEITvBofZcE4laPzx2csnDRfnQDiBZUFQcrHKX2whAKti+uWcPpY015LfwMxClNdx2zxe7NsCgfpSADpk3xkyPa6XdKW9QbwhctEJm62Hx92rOivGBQIR6BBgEW3MmM5guTfXjps+2kSVQ7TwkMese4GGLnFc/IuZIJR8ek9sLy7w7SzZLUrvIegbZtUhNUJPHN0b7auO55tuKqkGRc/NwNb1ZT+u60LVoC7XKEkFNGGX78KItDItReXK+nw3YcMGaOHJYu6jkm3AmroXgj2dmF6lERCgG9Eh2IEKkNt1gjpkm6skN09mAnfe4cmunt93UhCp/IcjGD4df32pDLsFwqknyj0GJ4kbDKAZCtwR8b1Pb1Zhfat97EJ4x8XmIZEjihGkn43T3t9ezskIUGInjGccMFBThgjxToWNVIzm2xSQg821OA+F+dGMRA0QlnEGeg3Hysvdcttnwq427uxvcTSSYbzgCkzKY3pX6OiNZzhFBETqmTZKgqiM3V3g5Bcj9VAi4gkBQ/EXjgHFvbxqRE7ffxgLfryfYWR5oWax4frZw== elijahk@NB-C02H10TSQ6LX"
cpu_nodes_count   = 3
gpu_nodes_count   = 1
gpu_nodes_preset  = "1gpu-20vcpu-200gb"
enable_grafana    = true
enable_prometheus = true
enable_loki       = true
enable_dcgm       = true

enable_filestore     = true
filestore_disk_size  = 42949672960
filestore_block_size = 4096

loki_aws_access_key_id = ""
loki_secret_key        = ""
