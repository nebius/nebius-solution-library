# Using MIG on Nebuis
This guide will explain the process of slicing a GPU on Nebius AI Cloud.

## Caveats
1) It is currently required to deploy a "driverless" cluster, i.e. a cluster without any drivers pre-installed.

## Install GPU Operator
`helm install --wait --generate-name -n gpu-operator --set migStrategy=single --create-namespace nvidia/gpu-operator --version=v25.3.2`
## Configuring MIG
1) Set cluster policy with ```helm install --wait --generate-name \
    -n gpu-operator --set migStrategy=single --create-namespace \
    nvidia/gpu-operator \
    --version=v25.3.2```
2) Pick a MIG profile that corresponds with your GPU SKU: https://docs.nvidia.com/datacenter/tesla/mig-user-guide/#supported-configurations
3) Configure MIG Strategy with `kubectl patch clusterpolicies.nvidia.com/cluster-policy --type='json' -p='[{"op":"replace", "path":"/spec/mig/strategy", "value":"single"}]’`
4) Label nodes with 1g.10gb profile: `kubectl label nodes <node-name> nvidia.com/mig.config=all-1g.18gb –overwrite`
5) Optionally, display Node Labels to verify configuration: `kubectl get node <node-name> -o=jsonpath='{.metadata.labels}' | jq .`
6) Use kubectl describe to verify MIG is enabled, it should look like:
```
Capacity:
  cpu:                     128
  ephemeral-storage:       97365936Ki
  hugepages-1Gi:           0
  hugepages-2Mi:           0
  memory:                  1651351216Ki
  nvidia.com/gpu:          0
  nvidia.com/mig-1g.18gb:  56
```

