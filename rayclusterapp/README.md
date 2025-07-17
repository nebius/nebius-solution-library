# Ray Cluster App Helm Chart
it's a helm chart to install a raycluster app

## Instructions to install Kuberay operator
```bash
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm repo update
helm install kuberay-operator kuberay/kuberay-operator --namespace kuberay --create-namespace
```

## Build a Docker Image for the Head, Worker and driver job pods
```bash
docker build -t rezabah/rayclusterapp-py39-cu128:0.1.1 .
docker push rezabah/rayclusterapp-py39-cu128:0.1.1
```

## Example of Installing a Ray Cluster App
### Make sure to set the values.yaml file based on youe settings
```bash
cd raycluster-app
helm dep update .
helm install rayapp1 . -f values.yaml --namespace rayapp1 --create-namespace
```
### Uninstall the helm release
```bash
helm uninstall rayapp1 -n rayapp1
```
