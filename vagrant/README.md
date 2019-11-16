0. Change your current working directory:
   ```
   cd <PATH_TO_ARTEMIS>/vagrant
   ```
1. Provision your VM for the first time (will lead to a reboot):
   ```
   ./vagrant up --provision
   ```
2. Turn your VM on (will automatically update and boot ARTEMIS):
   ```
   ./vagrant up
   ```
   *Note: the final output will be: "Visit ARTEMIS at: https://${artemis_host}". Note the IP address, which is the host-only address of the VM.*
3. Pause your VM (saving its current execution state):
   ```
   ./vagrant suspend
   ```
4. Turn your VM off (will automaticall shut ARTEMIS down):
   ```
   ./vagrant halt
   ```
5. Destroy your VM (*attention: this will also erase all VM data*):
   ```
   ./vagrant destroy
   ```
6. `ssh` into your VM (using the locally generated SSH key):
   ```
   ./vagrant ssh
   ```

Temporary VM data will be stored under `.vagrant`.
Please let the ARTEMIS devs know in case something does not work as expected.
The setup has been tested with VirtualBox 5+ and the latest vagrant executable (included in the folder).
