# Getting Started

Quick guide for getting started with kAFL for Confidential Compute hardening.

- For motivation and solution overview, refer to [Guest Hardening Strategy](https://intel.github.io/ccc-linux-guest-hardening-docs/tdx-guest-hardening.html#)
- For an overview of the workflow and tools, see [workflow overview](workflow_overview.md)


## 1. Prerequisites

- **Intel Skylake or later:** The setup requires a Gen-6 or newer Intel CPU (for
  Intel PT) and adequate memory (~2GB RAM per CPU, 5-20GB storage per campaign)

- **Patched Host Kernel:** A modifed Linux host kernel is used for TDX emulation
  and VM-based snapshot fuzzing. This setup does not run inside a VM or container!

- **Recent Debian/Ubuntu:** The userspace installation and fuzzing workflow has
  been tested for recent Ubuntu (>=20.04) and Debian (>=bullseye).

- **Know your Kernel:** Working knowledge of Linux console, kernel build and boot,
  and an idea of the kernel version and feature you want to test.


## 2. Installation

#### 2.1. Clone this repo to a new top-level workspace and install using `make deploy`:

  ```bash
  git clone https://github.com/intel/ccc-linux-guest-hardening ~/cocofuzz
  cd ~/cocofuzz
  make deploy
  ```

**Note:** The installation uses Ansible. The main system modification is to
install a patched host kernel (`.deb` package) and fixing the `grub` config to
make it boot. Ansible will also add the current user to group `kvm` and pull in
a few build dependencies and tools via `apt`. The rest of the stack consists of
userspace tools and scripts which are only available in a local Python virtual
environment.

#### 2.2. If not yet done, reboot to launch the kAFL/SDV emulation kernel:

```bash
uname -a
# Linux tdx-fuzz0 5.6.0-rc1-tdfl+ #15 SMP Wed May 25 02:23:44 CEST 2022 x86_64 x86_64 x86_64 GNU/Linux
```

```bash
dmesg|grep KVM-PT
# [KVM-PT] Info:  CPU is supported!
# [KVM-PT] Info:  LVT PMI handler registrated!
```

#### 2.3. Activate the environment and check if tools are available:

```bash
make env
fuzz.sh
exit
cat env.sh
```

**Note 1:** The environment defines various default paths used by multiple layers of
scripts. Go take a look. The script also sets `MAKEFLAGS="-j$(nproc)"` as a global
default for parallel builds. Watch out for effects of this.

**Note 2:** All subsequent steps assume to be executed from within this environment.
 

## 3. Launch a Pre-Defined Harness

Since our fuzzing target are components of a Linux VM guest, a "harness"
consists not only of a test function to inject input, but may also require
a specific guest kernel and VM configuration. In some cases, we may even
boot into a small userspace (initrd) to fuzz the kernel while executing
interesting Linux commands (usermode stimulus).

Multiple helpers are provided to generate a pre-defined harnesses. 

#### 3.1. Prepare global baseline assets (initrd, qemu disk image, sharedir)

```bash
make prepare
```

#### 3.2. Initialize a harness directory with desired setup, e.g. `POST_TRAP` harness:

```bash
init_harness.py ~/data/test1 BOOT_POST_TRAP 
```

#### 3.3. Build the target kernel (based on sources at `$LINUX_GUEST`)

```bash
cd ~/data/test1/BOOT_POST_TRAP
mkdir build
fuzz.sh build ./ build
```

#### 3.4. Launch kAFL based on assets/configs in $PWD:

```bash
cd ~/data/test1/BOOT_POST_TRAP
fuzz.sh run build -p 16 --redqueen --log-crashes
```

Open kAFL UI in another console on same system:

```bash
kafl_gui $KAFL_WORKDIR
```

Review the `fuzz.sh` helper to get an idea for how this works. Generally, the
script abstracts the most common usages of the kAFL fuzzer and ensures
that each usage (`kafl_fuzz.py`, `kafl_cov.py`, `kafl_debug.py`) is called with
the same consistent VM setup. Moreoever, it prefers local files and arguments over
global defaults to allow easy customization.

More more information about using kAFL, [see here (TBD)](https://wenzel.github.io/kAFL/).

## 4. Define a new Harness

Launching a custom harness is almost trivial at this point: modify the
Linux kernel build or `kafl.yaml` and re-start the fuzzer.

The interesting part is to identify an interface/function that should
be fuzzed, and interfacing with the guest kernel kAFL agent to perform the
desired input injection. To this end, start by reviewing the implementation and
configuration options for the guest-side input injection are described in [kAFL Agent
Implementation](kafl_agent.md). Take a look at some existing harness to understand
how injection is performed.

The following guides describe the different approaches in more detail:

- [Enumerating code paths with untrusted host input](https://intel.github.io/ccc-linux-guest-hardening-docs/tdx-guest-hardening.html#static-analyzer-and-code-audit)
- [Enabling and fuzzing a new guest driver](https://intel.github.io/ccc-linux-guest-hardening-docs/tdx-guest-hardening.html#enabling-additional-kernel-drivers)
- [Selective function fuzzing with KPROBE](example_targeted_fuzzing.md)
- [Fuzzing with userspace stimulus](userspace_stimulus.md)

Once you have defined a harness, step back to review the overall [recommended
workflow](workflow_overview.md) for obtaining coverage and reviewing fuzzer findings.

