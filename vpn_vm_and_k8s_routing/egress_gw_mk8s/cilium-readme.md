# Routing Traffic Through EgressGateway in Kubernetes

This tutorial explains how to configure a Cilium policy to route traffic from selected pods through an EgressGateway. This setup allows pods to share a single public IP for all outgoing traffic.

## Steps

1. **Enable EgressGateway on Cilium**

    Execute the following commands to configure your cluster for EgressGateway support:

    ```bash
    kubectl -n kube-system patch configmap cilium-config --patch '{"data":{"enable-ipv4-egress-gateway":"true"}}'
    kubectl rollout restart ds cilium -n kube-system
    kubectl rollout restart deploy cilium-operator -n kube-system
    ```

2. **Update and Apply the Cilium Policy**

    Edit `cilium-policy.yaml`, replacing placeholders with appropriate values:

    - `<POD-LABEL>`: Label of the target pods for which the policy should apply.
    - `<YOUR-NAMESPACE>`: Namespace where the target pods are running.
    - `<NODE-NAME>`: Name of the node that will act as the EgressGateway and should have a public IP.

    After updating the placeholders, apply the policy:

    ```bash
    kubectl apply -f cilium-policy.yaml
    ```

**Note**: Ensure the selected node (`<NODE-NAME>`) has a public IP to allow external access for outgoing traffic.

This configuration routes the traffic of specified pods through the EgressGateway node, using a single public IP for simplified egress control.
