# kAFL Fuzzing with Userspace Stimulus

This approach focuses on runtime activity of the Linux kernel. In contrast to
boot time fuzzing, a 'stimulus' is required to trigger various kernel activity,
which in turn may lead to reading untrusted input.

The approach the same kAFL agent as in boot time fuzzing to control the actual
input injection, intercepting kernel panic etc. This way, we only need to supply
a relevant stimulus program, and a loader script to initialize the agent and
execute the stimulus as desired.

The below examples use Busybox or Buildroot to create small VM images. It is
possible to use more common Linux distributions but the longer boot times and
RAM size will impact fuzzer startup time and ability to fuzz many VMs in
parallel.

_TODO:_
- virtio-blk is not yet supported, so we are limited to initramfs
- busybox image not really used here. Maybe simplify and use busybox scripts
  only as dummy initrd in boot time fuzzing (to trigger ABORT hypercall on
  userspace entry)

## Busybox RootFS

A rootfs based on [Busybox](https://busybox.net) is easy to build and small. It
is good for simple userspace apps that can be compiled as static or added
together with their dependencies (check ldd).

The following steps create, bless and package an initrd based on busybox:

```shell
$BKC_ROOT/bkc/kafl/userspace/gen_initrd.sh  initrd.rootfs
$BKC_ROOT/bkc/kafl/userspace/bless_initrd.sh initrd.rootfs
./initrd.rootfs/build.sh initrd.cpio.gz
```

Blessing means we add a `loader.sh` init script that will contact the host
kAFL fuzzer to download and execute a file `init.sh`. This is
used to bootstrap any desired userspace setup inside the guest (see below).

In the simplest case, we can use this to trigger an "abort" hypercall as soon as
Linux reaches userspace. This is useful in combination with boot time fuzzing,
where we don't expect to reach userspace and should raise a corresponding error:

```shell
cat > $BKC_ROOT/sharedir/init.sh << HERE
#!/bin/sh
/fuzz/habort "Error: guest execution reached userspace!"
HERE
```

The sharedir folder is automatically picked up by the `fuzz.sh` launcher and
init.sh is executed as the default loader inside the guest.


## Buildroot RootFS

[Buildroot](https://buildroot.org) is a framework for building small root filesystems. It allows to
include some standard tools and custom packages on top of busybox.

The provided example configuration
sets the correct target platform, initramfs output format, and selects some
basic Linux tools to use as stimulus (lspci, fio, stress-ng,..). The patches
include a newer version of stress-ng and add the perf\_fuzzer tool.

Quick install:

### 1. Download latest stable buildroot environment:

```shell
BUILDROOT_VERSION="buildroot-2021.11"
URL="https://buildroot.org/downloads/$BUILDROOT_VERSION.tar.gz"

wget $URL
tar xzf $(basename $URL)
```

### 2. Apply patches for newer stress-ng package and adding perf\_fuzzer tool:

```shell
cd $BUILDROOT_VERSION
git init .; git add .; git commit -m "vanilla $BUILDROOT_VERSION"
git am $BKC_ROOT/bkc/kafl/userspace/buildroot/0001-upgrade-to-stress-ng-0.13.05.patch
git am $BKC_ROOT/bkc/kafl/userspace/buildroot/0002-new-package-perf_fuzzer.patch
```

### 3. Apply / customize configuration and build. Initial build may take a while.

```shell
cp $BKC_ROOT/bkc/kafl/userspace/buildroot/buildroot.config .config
cp $BKC_ROOT/bkc/kafl/userspace/buildroot/busybox.config package/busybox/.config
#make menuconfig            # optional
#make busybox-menuconfig    # optional
make source                 # download packages up front
make -j $(nproc)
```

### 4. Bless the Buildroot rootfs

The provided `bless_initrd.sh` can be used again to update the buildroot init
flow and inject a loader.sh early on, which will in turn attempt to download and
execute a `init.sh` from the host kAFL `sharedir`.

Bless and rebuild the image, then copy or link it for use by fuzz.sh:

```shell
cd $BKC_ROOT
./bkc/kafl/userspace/bless_initrd.sh $BUILDROOT_VERSION/output/target/
make -C $BUILDROOT_VERSION
ln -sf  $BUILDROOT_VERSION/output/images/rootfs.cpio.gz $BKC_ROOT/initrd.cpio.gz
```

## Sharedir Setup

The kAFL `sharedir` feature offers an OS-independent interface for downloading
files from a host directory provided using the `kafl_fuzz.py --sharedir` option.

By default, the stage 1 `loader.sh` uses `hget` to request and execute an
`init.sh` script as the 2nd stage and perform actual harness initialization.
This allows to define the userpace harness or stimulus setup completely based on
files provided in the host-side sharedir.

A basic sharedir can be build from existing bkc/templates like this:

```shell
$BKC_ROOT/bkc/kafl/userspace/gen_sharedir.sh $BKC_ROOT/sharedir
```

To run the userspace harness, make sure the TDX guest kernel has the kAFL agent
activated with harness set to NONE. This disables any boot-time harnesses and
allows to boot through to the userspace loader.sh. Recommended settings:

```shell
cd $LINUX_GUEST
./scripts/config -e CONFIG_TDX_FUZZ_KAFL
./scripts/config -e CONFIG_TDX_FUZZ_KAFL_DEBUGFS
./scripts/config -e CONFIG_TDX_FUZZ_KAFL_SKIP_CPUID
./scripts/config -d CONFIG_TDX_FUZZ_KAFL_SKIP_PARAVIRT_REWRITE
./scripts/config -e CONFIG_TDX_FUZZ_HARNESS_NONE
```

The provided sharedir scripts analyze payloads using Linux gcov + trace events:
```shell
cd $LINUX_GUEST
./scripts/config -e CONFIG_GCOV_KERNEL
./scripts/config -e CONFIG_GCOV_PROFILE_ALL
./scripts/config -d GCOV_PROFILE_FTRACE
./scripts/config -e CONFIG_FTRACE
./scripts/config -e CONFIG_TRACING
./scripts/config -e CONFIG_EVENT_TRACING
#./scripts/config -e CONFIG_BOOTTIME_TRACING
```

Also recommend to disable `tdx_fuzz` event for the `tdg_fuzz_err()` hook, otherwise there
will be even more timer-based input events that we don't care about:

```diff
diff --git a/arch/x86/kernel/kafl-agent.c b/arch/x86/kernel/kafl-agent.c
index e31113b30014..425d211aa95f 100644
--- a/arch/x86/kernel/kafl-agent.c
+++ b/arch/x86/kernel/kafl-agent.c
@@ -434,7 +434,7 @@ bool tdg_fuzz_err(enum tdg_fuzz_loc type)
 {
        if (!fuzz_enabled || !fuzz_tderror) {
                // for filtering stimulus payloads, raise a trace event with
size=0 here
-               trace_tdx_fuzz((u64)__builtin_return_address(0), 0, 1, 1, type);
+               //trace_tdx_fuzz((u64)__builtin_return_address(0), 0, 1, 1,
                type);
                return false;
        }


```

And we seem to require a small patch for the guest kernel to boot with ftrace enabled:

```diff
diff --git a/arch/x86/kernel/tdx.c b/arch/x86/kernel/tdx.c
index 380fd05fe38a..81a6b5ec9874 100644
--- a/arch/x86/kernel/tdx.c
+++ b/arch/x86/kernel/tdx.c
@@ -96,10 +96,10 @@ static u64 _trace_tdx_hypercall(u64 fn, u64 r12, u64 r13, u64 r14, u64 r15,
 {
        u64 err;

-       trace_tdx_hypercall_enter_rcuidle(fn, r12, r13, r14, r15);
+       //trace_tdx_hypercall_enter_rcuidle(fn, r12, r13, r14, r15);
        err = _tdx_hypercall(fn, r12, r13, r14, r15, out);
-       trace_tdx_hypercall_exit_rcuidle(err, out->r11, out->r12, out->r13,
-                                        out->r14, out->r15);
+       //trace_tdx_hypercall_exit_rcuidle(err, out->r11, out->r12, out->r13,
+       //                               out->r14, out->r15);

        return err;
 }
```

Before building the final kernel, now is also a good time to generate a smatch
report for your current kernel. See the first part of below "Stimulus
Evaluation" section. Then continue to build the kernel as usual using `make -j <N>`.


Finally, review the launcher script `bkc/kafl/fuzz.sh` to ensure it picks up the
correct version of bzImage, initrd and sharedir. Once the `loader.sh` starts
properly, modifications should be mostly limited to the sharedir folder:

```
cd ~/tdx
ln -s bkc/kafl/fuzz.sh
ln -sf buildroot-2021.08/output/images/rootfs.cpio.gz initrd.cpio.gz
./fuzz.sh linux-guest -p 1 -sharedir ~/sharedir
```

Fuzzing complex user stimulus like `lspci` or `ping` may suffer from significant
non-determinism. Current best known option is to disable -funky and use
--log_crashes. Also ensure you set a sufficient timeout window, e.g. `-t 2 -ts 1`.
The new `--kickstart` option tends to work very well for building an initial
corpus. Also increase the VM RAM to at least 1G and look out for 'out of memory'
errors in the crash logs.

_TODO:_ Describe and provide sample/template scripts for both, stimulus
evaluation and currently recommended fuzz cases

## Stimulus Evaluation

Produce a smatch report for your kernel. The below helper will download and
build smatch as well as the guest-audit repo if not present, then run smatch on
the kernel to produce '~/tdx/linux-guest/smatch_warns.txt'. This file is also
picked up by `fuzz.sh` and placed in the `workdir/target/` folder for later use.

```
cd ~/tdx
./bkc/kafl/gen_smatch_warns.sh linux-guest
```

Finally, the below script will inspect the gcov/lcov traces produced by kAFL
userspace launcher (in `sharedir/init.sh`):

```
pip3 install gcovr
./bkc/kafl/userspace/minimize_stimulus.sh /path/to/workdir
```

It decompresses the individual payloads placed in `workdir/dump/`, inspects the
trace log, and performs gcov + smatch match analysis for any payload with new
`tdx_fuzz` events.

You can re-run the script whenever new results are uploaded to the dump/ folder.
Previously seen stacks are kept in dump/seen/.
