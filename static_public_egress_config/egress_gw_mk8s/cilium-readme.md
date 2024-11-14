# Routing Traffic Through EgressGateway in Kubernetes

This tutorial explains how to configure a Cilium policy to route traffic from selected pods through an EgressGateway. This setup allows pods to share a single public IP for all outgoing traffic.

## Steps

0. **Enable EgressGateway on Cilium**

    Create a support request to: 
     - Switch option "use network pools" for "IPv4 Private Pools" in "true" for existing subnet
     - Ask to create a new subnet, new static public IP pool with just one address (CIDR /32). Option "use network pools" for "IPv4 Private Pools" should also be in  "true" for this subnet
     - Newly created static public pull should have "use network pools" for the subnet in "false" state (so it would be accessible only from the subnet)

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
