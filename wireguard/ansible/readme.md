### This ansible playbook allows to configure custom DNS servers and custom routes for the VMs

- Ensure that the host machine has ansible installed, private SSH key is located in the ssh config folder is matching the key, target VMs were deployed with and the connection to those VMs is trusted (fingerprints known)
- Edit the file `hosts` to contain all target VM IP addresses, you can divide them in groups for your convinience
- Edit the `vars` section in the top of the `netplan.yml` according to desired configuration
- Once the configuration done, perform the command `ansible-playbook -i hosts netplan.yml` and wait for it's completion, it might take some time.
 - Note, that on successfull configration VMs will be rebooted
