# Ray Job Helm Chart
it's a helm chart to submit a Ray job to a Ray cluster

## Instructions to install Kuberay operator and a Ray cluster
### Make sure to set the raycluster-values.yaml file based on your settings
### Rayjob also has the capability to create a Ray cluster with the job submission at the same time
```bash
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm repo update
helm install kuberay-operator kuberay/kuberay-operator --namespace kuberay-operator --create-namespace
helm install raycluster1 kuberay/ray-cluster -f raycluster-values.yaml --namespace raycluster1 --create-namespace
```
----
## Build a Docker image for the Head, Worker and Driver job pods
### It's prefered to build one image for all 3 roles; here is an example:
```bash
docker build -t rezabah/rayclusterapp-py39-cu128:0.1.1 .
docker push rezabah/rayclusterapp-py39-cu128:0.1.1
```
### Build command for MAC Laptop with Arm cpu:
```bash
docker buildx build --platform linux/amd64 -t rezabah/rayclusterapp-py39-cu128:0.1.1 --push .
```
----
## Example of submitting a Ray job to the Ray Cluster using the helm chart
### Make sure to set the values.yaml file in the helm chart based on your settings
```bash
cd ray-job
helm install rayjob1 . -f values.yaml --namespace raycluster1
```
### Uninstall the helm release for the job
```bash
helm uninstall rayjob1 -n raycluster1
```
----
# Install Kueue for Gang Scheduling
## Install Kueue using Helm chart on your cluster
```bash
helm install kueue oci://registry.k8s.io/kueue/charts/kueue \
  --version=0.13.0 \
  --namespace  kueue-system \
  --create-namespace \
  --wait --timeout 300s
```
### Note: The Kueue resources will be installed using Ray job helm chart and will bootstrap your cluster as well


