# Getting Started

Quick guide for getting started with kAFL for Confidential Compute hardening.

- For motivation and solution overview, refer to [Guest Hardening Strategy](https://intel.github.io/ccc-linux-guest-hardening-docs/tdx-guest-hardening.html#)
- For an overview of the workflow and tools, see [workflow overview](workflow_overview.md)


## 1. Prerequisites

- **Intel Skylake or later:** The setup requires a Gen-6 or newer Intel CPU (for
  Intel PT) and adequate memory (~2GB RAM per CPU, 5-20GB storage per campaign)

- **Patched Host Kernel:** A modified Linux host kernel is used for TDX emulation
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

#### 3.2. (Optional) Build smatch cross-function database for better coverage results:

This is an optional step if you just want to try out the fuzzing, but it is highly
recommended to do before any real fuzzing is started since it improves greatly the precision
of the generated smatch audit log.

```bash
  cd ~/cocofuzz/linux-guest
  ../smatch/smatch_scripts/build_kernel_data.sh
```

The above would make a one full round of kernel compilation and build a resulting
smatch cross-function database in ~/cocofuzz/linux-guest/smatch_db.sqlite
The step should be *repeated 5-6 times* in total and with each iteration the database
size will grow and this will improve both the coverage and audit results.

After you have successfully build the cross-function database 5-6 times, the following
should be executed to generate an updated list of smatch audit entries:

```bash
cd ~/cocofuzz
make env
```

```bash
bkc/audit/smatch_audit.sh . bkc/kafl/linux_kernel_tdx_guest.config 
```

The step 3.2 is enough to do only once per each base upstream kernel version that
is being used as guest kernel since the database of cross functions does not change
drastically between different minor kernel versions. 

#### 3.3. Initialize a harness directory with desired setup, e.g. `POST_TRAP` harness:

For the following subsections, one must be in the environment:
```bash
make env
```

```bash
init_harness.py ~/data/test1 BOOT_POST_TRAP 
```

#### 3.4. Build the target kernel (based on sources at `$LINUX_GUEST`)

```bash
cd ~/data/test1/BOOT_POST_TRAP
mkdir build
fuzz.sh build ./ build
```

#### 3.5. Launch kAFL based on assets/configs in $PWD:

```bash
cd ~/data/test1/BOOT_POST_TRAP
fuzz.sh run build -p 16 --redqueen --log-crashes
```

During the fuzzing execution, there is an option to monitor fuzzing status through kAFL 
[user interface](https://intellabs.github.io/kAFL/reference/user_interface.html): 

Open another console, and switch to the ccc repository directory. If you followed the steps from
[here](https://github.com/intel/ccc-linux-guest-hardening#clone-this-repo-to-a-new-top-level-workspace-and-install-using-make-deploy)
it would be `~/cocofuzz` and be sure to enter the environment first.

```bash
make env
kafl_gui.py $KAFL_WORKDIR
```

#### 3.6. (Optional) Getting verbose output from the guest kernel
Some predefined harnesses will set [`log_crashes`](https://intellabs.github.io/kAFL/reference/fuzzer_configuration.html#log-crashes) in for the kAFL config in the build directory. For example:
```
# cat ~/data/test1/BOOT_POST_TRAP/kafl.yaml
abort_time: 2
trace: True
log_crashes: True
kickstart: 4
```
This is recommended to save space while collecting guest logs corresponding to irregular payloads. However, it _also truncates the main hprintf log after every execution_. 

Such verbosity can be useful in the case of debugging.  Instead, you can use [`log_hprintf`](https://intellabs.github.io/kAFL/reference/fuzzer_configuration.html#log-hprintf), as it allows a linear log of the guest executions across multiple snapshots/restores:
```
# the same kafl.yaml after overriding log_crashes with log_hprintf:
abort_time: 2
trace: True
log_hprintf: True
kickstart: 4
```
After the change, you could run the same fuzzing campaign with `fuzz.sh run build -p1` and observe the linear log from `$KAFL_WORKDIR/hprintf_00.log`.  If `log_crashes` is not present in the local kAFL config, you may use the [`--log-hprintf`](https://intellabs.github.io/kAFL/tutorials/fuzzing_linux_kernel.html#coverage) parameter directly. You may further increase verbosity via `hprintf=7` in the kAFL `qemu_append` [option](https://github.com/intel/ccc-linux-guest-hardening/blob/fd3e9c055476836d192a43074a7621e94afc5137/bkc/kafl/kafl_config.yaml#L7). Review [Fuzzer Configuration](https://intellabs.github.io/kAFL/reference/fuzzer_configuration.html#fuzzer-configuration) for more environment variables and command line switches.

Review the `fuzz.sh` helper to get an idea for how this works. Generally, the
script abstracts the most common usages of the kAFL fuzzer and ensures
that each usage (`kafl_fuzz.py`, `kafl_cov.py`, `kafl_debug.py`) is called with
the same consistent VM setup. Moreover, it prefers local files and arguments over
global defaults to allow easy customization.

For more information about using kAFL, [see here](https://wenzel.github.io/kAFL/).

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
- [Fuzzing with userspace stimulus](usermode_stimulus.md)

Once you have defined a harness, step back to review the overall [recommended
workflow](workflow_overview.md) for obtaining coverage and reviewing fuzzer findings.

