# Details on Ansible

inventory : Create an Ansible inventory file that lists the target systems you want to update. This file should contain the necessary details to connect to the systems, such as IP addresses.

<br />

system_credentials.yml : This file contains the credentials of the target systems.

<br />

Playbooks : Ansible playbooks are defined with the tasks required to update the different components of system firmware, fetch system firmware and GPU inventory for the supported Compute XD servers, and to check/change power state (on, off, reboot, AC power cycle) on Compute XD690 nodes.

<br />

Run the Playbooks : Execute the playbook using the ansible-playbook command, providing the inventory file and the playbook file as arguments. Ansible will connect to the target systems specified in the inventory and execute the tasks defined in the playbook.

<br />

logs/ : Every playbook writes its results (firmware inventory, GPU inventory, firmware update status, power state) to a JSON/CSV file in this folder - one file per host, per run, so you always have a record of what happened.



# Ansible Firmware Update Tool

This repository contains ansible modules, playbooks to perform firmware upgrade HPE Compute XD690



# Pre-requisites

1. Ansible should be installed

2. Ansible collection module community.general >= 6.4.0



To install Community general package use:



```

ansible-galaxy collection install community.general

```

3. Run the OS-specific setup playbook (in `setup/`) to install ipmitool required for Power cycle

```

ansible-playbook -i inventory setup/ubuntu_setup.yml

```

(use `setup/RHEL_setup.yml` or `setup/SUSE_setup.yml` instead, depending on the control node's OS)



# Update inventory and system_credentials.yml

Update the IP address under [xds] variable like the below:

```

[xds]

ip1

ip2

```

Update the IP address its corresponding username and password in system_credentials.yml as follows:

```

---

inputs:

   ip1:

      user: "<ip1 user name>"

      password: "<ip1 password"

   ip2:

      user: "<ip2 user name>"

      password: "<ip2 password>"



```



# Scripts

1. system_firmware_update.yml : Playbook to perform firmware upgrade - the list of firmware (.fwpkg) files to flash, and the order to flash them in, is set in the `[Firmware_Order_XD690]` section of config.ini

2. get_system_firmware_inventory.yml : Playbook to fetch the system firmware inventory information

3. power_control.yml: Playbook to check or change power state on the Compute XD690 nodes - power on, power off, reboot, or an IPMI AC power cycle, based on the `power_state` option in config.ini.
   
4. get_gpu_inventory.yml : Playbook to fetch the gpu inventory information


# Targets supported for Updates:

For HPE Compute XD690 supported targets are:

- BMC 
	
- BIOS

- MB CPLD

- DC_SCM CPLD

- BP CPLD
  
- E1 CPLD

- GPU/HGX firmware bundle (flashed the same way as the targets above - see Firmware Upgrade section)


# Firmware Upgrade


The playbook `system_firmware_update.yml` is used to perform the firmware upgrade and the detailed procedure is listed below:

1. Update system_credentials.yml and Compute servers details in the inventory file under [xds] Specifically the remotely accessible Compute ip addresses

2. Update the config.ini

   - Under `[Firmware_Order_XD690]`, list the firmware files (.fwpkg) you want to flash, one per line, numbered in the order you want them flashed (1, 2, 3, ...). This works for BMC, BIOS, CPLD, and GPU/HGX firmware alike - just add the file path.
   - For a single/individual firmware update, just list one entry (e.g. only `1 = <path>`).

3. Run the ansible playbook:

   ```ansible-playbook -i inventory system_firmware_update.yml -e @system_credentials.yml -e @Compute-vault --ask-vault-pass```

   (`-e @Compute-vault --ask-vault-pass` is optional - only needed if you're using an ansible-vault encrypted credentials file)

   Each firmware in the list is flashed one at a time, in order. If any of them fails, the run stops there and the remaining firmware in the list is not flashed.

   Once every firmware in the list has been flashed successfully, the tool automatically reboots the system (and runs an IPMI AC power cycle too, if any CPLD firmware was included) so everything takes effect - this only happens once at the very end, not after each individual firmware.

   Results for every step, including firmware version before/after, are saved to a JSON file under the `logs/` folder (one file per host, per run).



# Firmware Inventory

The playbook `get_system_firmware_inventory.yml` is used to fetch the firmware inventory information of the Compute servers

1. Update the following details in inputs.yml and inventory file accordingly

2. Run the ansible playbook:

   `ansible-playbook -i inventory get_system_firmware_inventory.yml  -e @system_credentials.yml`

   Results are saved to a JSON file under the `logs/` folder.


# GPU Inventory

The playbook `get_gpu_inventory.yml` is used to fetch the GPU/HGX firmware inventory information of the Compute servers

1. Update the following details in inputs.yml and inventory file accordingly

2. Run the ansible playbook:

   `ansible-playbook -i inventory get_gpu_inventory.yml  -e @system_credentials.yml`

   Results are saved to a JSON file under the `logs/` folder.


# Power Control

The playbook `power_control.yml` is used to check or change the power state of a Compute server.

1. Update the `power_state` option under `[Options]` in config.ini to one of:

   - `NA` - just report the current power state, no action
   - `on` - power the system on if it's currently off
   - `off` - power the system off if it's currently on
   - `reboot` - graceful reboot (same action the tool runs automatically after a BIOS/CPLD firmware update)
   - `ac_cycle` - IPMI AC power cycle (same action the tool runs automatically after a CPLD firmware update)

2. Run the ansible playbook:

   `ansible-playbook -i inventory power_control.yml -e @system_credentials.yml`

   Result is saved to a CSV file under the `logs/` folder.


# Ansible-vault

This ansible-vault encrypts the file containing sensitive data. And can be used during execution by providing the key.



To encrypt the file

```

ansible-vault encrypt file_name

```



To decypt the file 

```

ansible-vault decrypt file_name

```



To edit the file

```

ansible-vault edit file_name

```
