# Ray Cluster Job Helm Chart
it's a helm chart to submit a Ray job to a Ray cluster

## Instructions to install Kuberay operator and a Ray cluster
### Make sure to set the raycluster-values.yaml file based on your settings
```bash
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm repo update
helm install kuberay-operator kuberay/kuberay-operator --namespace kuberay-operator --create-namespace
helm install raycluster1 kuberay/ray-cluster -f raycluster-values.yaml --namespace raycluster1 --create-namespace
```

## Build a Docker image for the Head, Worker and Driver job pods
### It's prefered to build one image for all 3 roles; here is an example:
```bash
docker build -t rezabah/rayclusterapp-py39-cu128:0.1.1 .
docker push rezabah/rayclusterapp-py39-cu128:0.1.1
```
### Build command that should be used On MAC Laptop with Arm cpu:
```bash
docker buildx build \
  --platform linux/amd64 \
  -t rezabah/rayclusterapp-py39-cu128:0.1.1 \
  --push \
  .
```

## Example of submitting a Ray job to the Ray Cluster
### Make sure to set the values.yaml file in the helm chart based on your settings
```bash
cd ray-job
helm install rayjob1 . -f values.yaml --namespace raycluster1
```
### Uninstall the helm release for the job
```bash
helm uninstall rayjob1 -n raycluster1
```
