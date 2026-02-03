# NIMS Kubernetes Terraform Module

This Terraform module deploys a **Kubernetes namespace** with secrets and a **LoadBalancer service** for protein-related applications such as OpenFold, Boltz2, EVO2, and MSA search. It is designed to run on a cloud Kubernetes cluster with GPU support.

---

## Features

- Creates a dedicated Kubernetes **namespace**.
- Creates **Docker registry secret** for `nvcr.io` to pull NVIDIA container images using an NGC key.
- Creates a **NGC API key secret** for accessing NVIDIA services.
- Deploys a **single LoadBalancer service** exposing multiple applications on different ports.
  - OpenFold3 → port 8000  
  - Boltz2 → port 8001  
  - EVO2-40b → port 8002  
  - MSA Search → port 8003  
  - OpenFold2 → port 8004
- Uses model cache on shared filesystem
- Creates bionemo instances (on a seperate load balancer)
---
