1. To turn your VM on:
   ```
   ./vagrant up
   ```
   *Note 1: the first up will also provision the VM, and will cause a reboot. Just run an "up" again after this happens.*

   *Note 2: the final output (after reboot and the 2nd "up")  will be: "Visit ARTEMIS at: https://${artemis_host}". Note the IP address, which is the host-only address of the VM.*

2. To pause your VM:
   ```
   ./vagrant suspend
   ```
3. To turn your VM off:
   ```
   ./vagrant halt
   ```
4. To destroy your VM:
   ```
   ./vagrant destroy
   ```
5. To ssh into your VM:
   ```
   ./vagrant ssh
   ```
