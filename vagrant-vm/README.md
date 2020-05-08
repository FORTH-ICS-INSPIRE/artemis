1. Install the latest version of VirtualBox from [here](https://www.virtualbox.org/wiki/Downloads) (depending on your OS, etc.)
2. Install the latest version of `vagrant` from [here](https://www.vagrantup.com/downloads.html) (depending on your OS, etc.)
3. Change your current working directory:
   ```
   cd <PATH_TO_ARTEMIS>/vagrant-vm
   ```
4. Provision your VM for the first time (will lead to a reboot):
   ```
   vagrant up --provision
   ```
5. Turn your VM on (will automatically update and boot ARTEMIS):
   ```
   vagrant up
   ```
   *Note: the final output will be: "Visit ARTEMIS at: https://${artemis_host}". Note the IP address, which is the host-only address of the VM.*
6. Pause your VM (saving its current execution state) [optional]:
   ```
   vagrant suspend
   ```
7. Turn your VM off (will automatically shut ARTEMIS down):
   ```
   vagrant halt
   ```
8. Destroy your VM (*attention: this will also erase all VM data*):
   ```
   vagrant destroy
   ```
9. `ssh` into your VM (using the locally generated SSH key) [optional]:
   ```
   vagrant ssh
   ```

Temporary VM data will be stored under `.vagrant`.
Please let the ARTEMIS devs know in case something does not work as expected.
The setup has been tested with VirtualBox 5+ and the latest vagrant executable on a Linux Ubuntu 16.04 Desktop environment.
