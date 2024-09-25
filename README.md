PROJECT NOT UNDER ACTIVE MANAGEMENT

This project will no longer be maintained by Intel.

Intel has ceased development and contributions including, but not limited to, maintenance, bug fixes, new releases, or updates, to this project.  

Intel no longer accepts patches to this project.

If you have an ongoing need to use this project, are interested in independently developing it, or would like to maintain patches for the open source software community, please create your own fork of this project.  

Contact: webadmin@linux.intel.com
<h1 align="center">
  <br>Linux Security Hardening for Confidential Compute</br>
</h1>

<p align="center">
  <a href="https://github.com/intel/ccc-linux-guest-hardening/actions/workflows/ci.yml">
    <img src="https://github.com/intel/ccc-linux-guest-hardening/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
</p>

This project contains tools, scripts, and _best-known-configuration_ (BKC) for
Linux guest kernel hardening in the context of Confidential Cloud Computing threat
model. For motivation and solution overview, refer to
[Guest Hardening Strategy](https://intel.github.io/ccc-linux-guest-hardening-docs/tdx-guest-hardening.html#).

All components and scripts are provided for research and validation purposes only.

# Project overview:

In the [`bkc`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc) directory, you will find:

- [`audit`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/audit): threat surface enumeration using static analysis
- [`kafl`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/kafl): configs and tools for Linux fuzzing with kAFL
- [`syzkaller`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/syzkaller): configs and tools for generating guest activity with Syzkaller
- [`coverage`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/coverage): tools for matching coverage and trace data against audit list

# Getting started

## Requirements

- **Intel Skylake or later:** The setup requires a Gen-6 or newer Intel CPU (for
  Intel PT) and adequate memory (~2GB RAM per CPU, 5-20GB storage per campaign)

- **Patched Host Kernel:** A modified Linux host kernel is used for TDX emulation
  and VM-based snapshot fuzzing. This setup does not run inside a VM or container!

- **Recent Debian/Ubuntu:** The userspace installation and fuzzing workflow has
  been tested for recent Ubuntu (>=20.04) and Debian (>=bullseye).

- **Know your Kernel:** Working knowledge of Linux console, kernel build and boot,
  and an idea of the kernel version and feature you want to test.

## Installation

#### The installation and the fuzzing runtime requires Python3 and the virtual environment package:

~~~
sudo apt-get install python3 python3-venv
~~~

#### Clone this repo to a new top-level workspace and install using `make deploy`:

  ```bash
  git clone https://github.com/intel/ccc-linux-guest-hardening ~/cocofuzz
  cd ~/cocofuzz
  make deploy
  ```

**Note:** The installation uses [Ansible](https://docs.ansible.com/ansible/latest/).
The main system modification is to install a patched host kernel (`.deb` package)
and fixing the `grub` config to make it boot. Ansible will also add the current
user to group `kvm` and pull in a few build dependencies and tools via `apt`. 
The rest of the stack consists of userspace tools and scripts which are only 
available in a local Python virtual environment.

#### If not yet done, reboot to launch the kAFL/SDV emulation kernel:

```bash
uname -a
# Linux tdx-fuzz0 6.1.0-sdv+ #15 SMP Wed May 25 02:23:44 CEST 2022 x86_64 x86_64 x86_64 GNU/Linux
```

```bash
dmesg|grep KVM-NYX
# [KVM-NYX] Info:  CPU is supported!
# [KVM-NYX] Info:  LVT PMI handler registrated!
```

**Note:** When launching the kAFL/SDV emulation kernel, you might encounter an
initramfs unpacking [failure](https://github.com/intel/ccc-linux-guest-hardening/issues/90)
because [the current kernel lacks support for the `zstd` compression algorithm](https://github.com/intel/ccc-linux-guest-hardening/issues/90#issuecomment-1458468480).

To fix this, follow the steps below:
1. Edit `/etc/initramfs-tools/initramfs.conf` to change the compression
algorithm from `zstd` to, e.g., `lz4`
2. Rebuild the initramfs: `sudo update-initramfs -c -k all`
3. Select the kAFL/SDV emulation kernel after a reboot

The `zstd` support will be provided in the future kAFL/SDV emulation kernel.


## Activate the environment and check if tools are available:

When the installation is complete, you will find several tools and scripts 
(e.g., [`fuzz.sh`](bkc/kafl/fuzz.sh)) inside the installation directory of the target system.

All subsequent steps assume that you have activated the installation environment 
using `make env`:

```bash
make env
fuzz.sh
exit
```

The environment defines various default paths used by multiple layers of
scripts. Go take a look. Note that the script also sets `MAKEFLAGS="-j$(nproc)"`
as a global default for parallel builds:

```bash
make env
cat env.sh
echo $MAKEFLAGS
echo $KAFL_WORKSPACE
```

# Kernel Hardening Workflow

Now that the necessary components are installed, you can pursue by one the following:

1. [Review the campaign workflow and the automation tools](docs/workflow_overview.md)
2. [Generate smatch audit list](docs/generate_smatch_audit_list.md)
3. [Launch a Pre-Defined Harness](docs/getting_started.md#3-launch-a-pre-defined-harness)
4. [Explore how to define new harnesses](docs/getting_started.md#4-define-a-new-harness)
5. [Targeting your own guest kernel](docs/guest_kernel_changes.md)
