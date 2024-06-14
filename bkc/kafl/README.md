# kAFL/Nyx for TDX Guest Fuzzing

kAFL/Nyx is a fuzzer for Qemu/KVM VMs. This setup describes the combination of
kAFL with TDX SDV, to allows execution and fuzzing of TDX guests in kAFL.

**Platform requirements:** This setup requires a Gen-6 or newer Intel CPU (for Intel PT) and a modifed host kernel. It does not work in a VM or container.

## kAFL Hello World Example

__TODO:__ update and split out different example harnesses as subsections

kAFL requires the guest OS to implements an 'agent' which communicates with
the fuzzer using hypercalls and shared memory. There are two basic approaches.

1. Boot to userspace and initiate the agent via cron/systemd and `kafl fuzz -sharedir`
2. Integrate the agent into the Linux kernel to start fuzzing before userspace is up

For simpler first option is described below. 
For fuzzing from userspace please follow `./userspace/README.md`.

## Linux Boot Fuzzing


### 1. Build the Guest Kernel

Build a guest kernel with enabled kAFL agent and the desired selection of
harness and injection options. The below example activates the `POST_TRAP`
harness in `$LINUX_GUEST/init/main.c`:

```shell
cd $LINUX_GUEST
cp $BKC_ROOT/bkc/kafl/linux_kernel_tdx_guest.config .config
./scripts/config -e CONFIG_TDX_FUZZ_KAFL
./scripts/config -e CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_VIRTIO
[...]
make -j$(nproc)
```

### 2. Launching the Fuzzer

The fuzz.sh launch script pulls the various required components together for
launching with the kAFL fuzzer, coverage and debug tools. In particular:

- linux `bzImage` - taken from the target folder (second argument to `fuzz.sh`)
- initrd in `$BKC_ROOT/initrd.cpio.gz` - customize this for userspace fuzzing
- TDVF image at `$BKC_ROOT/TDVF.fd` - either based on prebuild or own TDVF build
- sharedir directory in `$BKC_ROOT/sharedir`  - customize for userspace fuzzing

Make sure that all the relevant assets exist. For kernel
fuzzing, any dummy initrd can be used (copy one from /boot).

To launch with bzImage taken from `linux-guest/` (aka. `$LINUX_GUEST`) directory:

```shell
ln -s ./bkc/kafl/fuzz.sh
#ln -s $TDVF_ROOT/Build/OvmfX64/DEBUG_GCC5/FV/OVMF.fd TDVF.fd  # own build?
ln -s TDVF_sdv_1G.fd TDVF.fd                                   # prebuild?
ln -s /boot/initrd.img-$(uname -r) initrd.cpio.gz
./fuzz.sh run linux-guest -t 2 -ts 1 -p 2 --log-hprintf
```

The default work directory of the fuzzer is based on $KAFL\_WORKDIR default
variable that is defined in your environment. To view more detailed fuzzer
status, open another terminal and open the kAFL GUI:

```shell
make env
kafl_gui.py $KAFL_WORKDIR
```

## Next Steps

The `fuzz.sh` laucher encapsulates the most common usages such as fuzzing,
coverage analysis, and debugging a payload. You can provide additional arguments
to `fuzz.sh` to override kAFL defaults. Some interesting options:

```shell
./fuzz.sh help 

./fuzz.sh run linux-guest -h
./fuzz.sh run linux-guest -p 16 # launch 16 VMs on first 16 logical cores
./fuzz.sh run linux-guest -p 32 --log-crashes # keep only crash logs at workdir/logs/
./fuzz.sh run linux-guest --debug --log-hprintf --log # run fuzzer but also guest with extra verbosity
```

The kAFL launch options are derived based on
1. hardcoded program defaults (`kafl_fuzzer/common/config.py`)
2. yaml configuration file (check `$KAFL_CONFIG_FILE` in your workspace)
3. command line arguments hardcoded into `fuzz.sh` or supplied by user


Check the [kAFL documentation](https://github.com/IntelLabs/kAFL) additional detail on kAFL operation and tools.

__TODO:__ expand kAFL documentation to explain different tools, outputs, options
in more detail


### kAFL Harness options

Common harnesses and fixes/options are exposed and documented in Linux Kconfig:

```ini
CONFIG_TDX_FUZZ_KAFL=y
CONFIG_TDX_FUZZ_KAFL_DETERMINISTIC=y
CONFIG_TDX_FUZZ_KAFL_DEBUGFS=y
# CONFIG_TDX_FUZZ_KAFL_TRACE_LOCATIONS is not set
CONFIG_TDX_FUZZ_KAFL_VIRTIO=y
CONFIG_TDX_FUZZ_KAFL_SKIP_CPUID=y
# CONFIG_TDX_FUZZ_KAFL_SKIP_IOAPIC_READS is not set
CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO=y
CONFIG_TDX_FUZZ_KAFL_SKIP_RNG_SEEDING=y
# CONFIG_TDX_FUZZ_KAFL_SKIP_PARAVIRT_REWRITE is not set
# CONFIG_TDX_FUZZ_HARNESS_NONE is not set
# CONFIG_TDX_FUZZ_HARNESS_EARLYBOOT is not set
CONFIG_TDX_FUZZ_HARNESS_POST_TRAP=y
# CONFIG_TDX_FUZZ_HARNESS_START_KERNEL is not set
# CONFIG_TDX_FUZZ_HARNESS_REST_INIT is not set
# CONFIG_TDX_FUZZ_HARNESS_DO_BASIC is not set
# CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS is not set
# CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_PCI is not set
# CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_VIRTIO is not set
# CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_ACPI is not set
# CONFIG_TDX_FUZZ_HARNESS_FULL_BOOT is not set
```

### Selective kprobe-based harnessing for Linux

We have included funcitonality to setup custom small harnesses for specific
target functions. These can for example be used for quickly reproducing bugs,
or for setting up more targeted fuzzing for certain subsystems. In a nutshell,
this sets up a kretprobe around a target function, taking a snapshot at
function entry and resetting at function return. Similarly, we also support
selectively disabling fuzzing mutation for particular functions; which is
useful for functions where the fuzzer might get stuck or for circumventing
known crashes.

Selectively disable mutation using the following kernel boot param:
`fuzzing_disallow=myfunc1,myfunc2,myfunc3`

Enable single function harnessing using kprobes:
`fuzzing_func_harness=myfunc`
Recommended to use `CONFIG_TDX_FUZZ_HARNESS_NONE` when using single function
harness.

You can set additional boot parameters in kAFL using the `KERNEL_BOOT_PARAMS`
environmental  variable. For example, to set up a single function harness for
the function `acpi_init` with mutation disabled for `acpi_scan_init`, run
something like the following command:

```shell
KERNEL_BOOT_PARAMS="fuzzing_func_harness=acpi_init fuzzing_disallow=acpi_scan_init" ./fuzz.sh full linux-guest
```

The single func harness/ fuzzing filter are setup using the functions
`tdx_fuzz_func_harness_init` and `tdx_fuzz_filter_init`. These are registered as
`core_initcalls` (level 1), since they depend on some memory management being
setup and kprobes working correctly. As such, this functionality is not
available to functions that are executed before these have been initialized.
A user can also programmatically enable filtering and single function
harnessing using the following functions:

```c
void kafl_fuzz_function(char *fname); // Harness around a single function fname
void kafl_fuzz_function_disable(char *fname); // Disable fuzz input consumption for fname
```

Here is an [example](../../docs/example_targeted_fuzzing.md) of using kprobe-based harnessing for targeted fuzzing.