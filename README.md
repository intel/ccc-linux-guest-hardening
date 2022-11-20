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
model. For motivation and solution overview, refer to [Guest Hardening Strategy](https://intel.github.io/ccc-linux-guest-hardening-docs/tdx-guest-hardening.html#).

All components and scripts are provided for research and validation purposes only.

# Project overview:

In the [`bkc`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc) directory, you will find:

- [`audit`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/audit): threat surface enumeration using static analysis
- [`kafl`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/kafl): configs and tools for Linux fuzzing with kAFL
- [`syzkaller`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/syzkaller): configs and tools for generating guest activity with Syzkaller
- [`coverage`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/coverage): tools for matching coverage and trace data against audit list

# Getting started

## Platform Requirements

- **Intel Skylake or later:** The setup requires a Gen-6 or newer Intel CPU (for
  Intel PT) and adequate memory (~2GB RAM per CPU, 5-20GB storage per campaign)

- **Patched Host Kernel:** A modified Linux host kernel is used for TDX emulation
  and VM-based snapshot fuzzing. This setup does not run inside a VM or container!

- **Recent Debian/Ubuntu:** The userspace installation and fuzzing workflow has
  been tested for recent Ubuntu (>=20.04) and Debian (>=bullseye).

- **Know your Kernel:** Working knowledge of Linux console, kernel build and boot,
  and an idea of the kernel version and feature you want to test.

## Installation

### The installation and the fuzzing runtime requires Python3 and the virtual environment package:

~~~
sudo apt-get install python3 python3-venv
~~~

### Clone this repo to a new top-level workspace and install using `make deploy`:

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

### If not yet done, reboot to launch the kAFL/SDV emulation kernel:

```bash
uname -a
# Linux tdx-fuzz0 5.6.0-rc1-tdfl+ #15 SMP Wed May 25 02:23:44 CEST 2022 x86_64 x86_64 x86_64 GNU/Linux
```

```bash
dmesg|grep KVM-PT
# [KVM-PT] Info:  CPU is supported!
# [KVM-PT] Info:  LVT PMI handler registrated!
```



## Activate the environment

When the installation is complete, you will find several tools and scripts
inside the installation directory of the target system.

The environment defines various default paths used by multiple layers of
scripts. Go take a look. The script also sets `MAKEFLAGS="-j$(nproc)"` as a global
default for parallel builds. Watch out for effects of this.

All subsequent steps assume that you have activated the installation environment.
This is done either by sourcing the `env.sh` script, or by typing `make env`,
which launches a sub-shell that makes it easier to exit and switch environments:

```shell
make env
```

# Kernel Hardening Workflow

Now that the necessary components are installed, you can pursue by one the following:

1. [Review the campaign workflow and the automation tools](docs/workflow_overview.md)
2. [Generate smatch audit list](docs/generate_smatch_audit_list.md)
3. [Run kAFL boot and usermode harnesses](bkc/kafl)
4. [Launch a Pre-Defined Harness](docs/getting_started.md#3-launch-a-pre-defined-harness)
5. [Explore how to define new harnesses](docs/getting_started.md#4-define-a-new-harness)

# Targeting your own guest kernel [TBD]

1. Port the provided guest kernel harnesses to your target kernel
2. Set `$LINUX_GUEST` to your target kernel source tree
3. Perform the above workflow steps based on your new target kernel
