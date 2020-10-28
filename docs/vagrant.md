We use [`vagrant`](https://www.vagrantup.com/) and [`VirtualBox`](https://www.virtualbox.org/) for VM automation.

To setup the VM, we recommend going over the steps described in [this README](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/vagrant-vm/README.md).

Note that we have tested the steps on a Linux Ubuntu 16.04+, using the latest `vagrant` and `VirtualBox` versions.
The spinned VM runs on 4 CPUs with 4G of RAM, hosts an ubuntu/bionic64 version of Ubuntu Server, and uses the default `vagrant` credentials (incl. a locally created SSH key) for access.

**Note that spinning up the VM in a single command is done for convenience in testing; if you want to use the VM in production we highly recommend that you change the default security settings (`ADMIN` credentials, secrets and certificates) as described in the [ARTEMIS tool setup docs page](https://bgpartemis.readthedocs.io/en/latest/overview/#setup-tool).**

Please let the dev team know on slack is something does not work on other OSes (e.g., MAC OS, Windows); however, this is typically a problem with `vagrant` compatibility rather than something specifically related to ARTEMIS. In case you would like to use another VM hypervisor (e.g., VMWare), this is also possible and we would appreciate any contributions and alternative vagrantfiles to support this.

In case we have missed anything in the steps/workflow, please feel free to edit the current docs page or issue a PR for the vagrant README.
