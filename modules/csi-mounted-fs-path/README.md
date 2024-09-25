## Accessing Storage

### Prerequisites:

1. To use csi-driver, it's mandatory to set 'enable_filestore = true' in terraform.tfvars file (relevant for k8s-inference & k8-training solutions) - While 'enable_filestore = true' then a File Storage disk will be created, and will be mounted to each node in all of your mk8s node groups.
2. For other solutions, that are not based on 'k8-inference' or 'k8s-training', please keep in mind that in order for the csi-driver to successfully work, a File Storage disk must be attached to all nodes in all of your managed-kubernetes node groups, here's a few steps to ensure those requirements:

    2.1 Create a File Storage disk:
    
    ```shell
        resource "nebius_compute_v1_filesystem" "shared-filesystem" {
            count            = var.enable_filestore ? 1 : 0
            parent_id        = var.parent_id
            name             = join("-", ["filesystem-tf", local.release-suffix])
            type             = var.filestore_disk_type
            size_bytes       = var.filestore_disk_size
            block_size_bytes = var.filestore_block_size # works better with 4K
        }
    ```
    2.2 Attach File storage to your node-group Terraform configurations:
   
        ```shell
        resource "nebius_mk8s_v1_node_group" "cpu/gpu-only-node-group" {
        ...Rest of your code
        filesystems = var.enable_filestore ? [
        {
            attach_mode         = "READ_WRITE"
            mount_tag           = "data"
            existing_filesystem = nebius_compute_v1_filesystem.shared-filesystem[0]
        }
        ] : null
        ...Rest of your code
        }
        ```
    2.3 Add to your Terraform node groups configuration the following cloud-init call:
   
        ```shell
        resource "nebius_mk8s_v1_node_group" "cpu/gpu-only-node-group" {
        ...Rest of your code
            cloud_init_user_data = templatefile("../modules/cloud-init/k8s-cloud-init.tftpl", {
                enable_filestore = var.enable_filestore ? "true" : "false",
                ssh_user_name    = var.ssh_user_name,
                ssh_public_key   = local.ssh_public_key
            })
        ...Rest of your code
        }
        ```
    2.4 Here's an example of cloud-init that mounts the attached File Storage disk to each instance, during instances boot:
   
    ```shell
    %{ if enable_filestore != "false" || enable_glusterfs != "false" }
    bootcmd:
    %{ endif }
    %{ if enable_filestore != "false" }
    - sudo mkdir -p /mnt/data # <--- This line is mandatory for csi-driver to work properly
    - sudo mount -t virtiofs data /mnt/data # <--- This line is mandatory for csi-driver to work properly
    - echo data /mnt/data \"virtiofs\" \"defaults\" \"0\" \"2\" | sudo tee -a /etc/fstab" # <--- This line is mandatory for csi-driver to work properly
    %{ endif }

    users:
    - name: ${ssh_user_name}
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
        - ${ssh_public_key}
    ```

    
4. Deploy csi-driver by applying the module: "csi-mounted-fs-path":
```shell
    module "csi-mounted-fs-path" {
        source = "../modules/csi-mounted-fs-path"
        count  = var.enable_filestore ? 1 : 0
    }
```


### Using the csi-driver
Using mounted storage requires manually creating Persistent Volumes. Bellow is a template for creating PV and PVC.
Replace `<HOST-PATH>` and `<SIZE>` variables with actual values.
* storageclass has to be equal to: 'csi-mounted-fs-path-sc'

```yaml
kind: PersistentVolume
apiVersion: v1
metadata:
  name: external-storage-persistent-volume
spec:
  storageClassName: csi-mounted-fs-path-sc
  capacity:
    storage: "<SIZE>"
  accessModes:
    - ReadWriteMany
  hostPath:
    path: "<HOST-PATH>" # "/mnt/data/<sub-directory>" or "/mnt/glusterfs/<sub-directory>"

---

kind: PersistentVolumeClaim
apiVersion: v1
metadata:
  name: external-storage-persistent-volumeclaim
spec:
  storageClassName: csi-mounted-fs-path-sc
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: "<SIZE>"
```


CSI limitations:
limitations of CSI over mounted FS
FS should be mounted to all NodeGroups, because PV attachmend to pod runniing on Node without FS will fail
One PV may fill up to all common FS size
FS size will not be autoupdated if PV size exceed it spec size
FS size for now can't be updated through API, only through NEBOPS. (thread)
volumeMode: Block  - is not possible

Good to know:
read-write many mode PV will work
MSP started testing that solution to enable early integration with mk8s. Hope they will bring feedback soon.
