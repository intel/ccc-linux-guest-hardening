# TDX: Running syzkaller + with Qemu

## Host OS:
Recommended OS is Ubuntu 20.04, mostly because it contains GCC 9 and our host kernel
doesn't contain patches which enabled GCC 10+ (will not boot and compile without additional patches).

## Host Kernel:
ssh://git@gitlab.devtools.intel.com:29418/tdx/guest.git 
sdv branch + host.config
guest-kernel.config is based on sdv/sdfuzz.config
```
make  binrpm-pkg -j`nproc`
```
Install kernel RPM package, reboot select kernel version in advanced boot options.


## Guest OS:
To build guest image run the following:
```
cd build
make guest-image
```

This will take a while, but after all you will have a ready to use Linux guest image
available in the build/image/stretch.img along with SSH keys stretch.id_rsa
Image will have 10GB in size, which should be sufficient for our needs.

We use sligthly modified version of the method described below:
https://github.com/google/syzkaller/blob/master/docs/linux/setup_ubuntu-host_qemu-vm_x86-64-kernel.md#image

## Guest BIOS
Use TDVF-acpitest-072120.fd from bkc/sdv directory

## Guest Kernel
Currently syzkaller uses tdx/fuzz-8 branch + guest.config,
with additional settings based on: https://github.com/google/syzkaller/blob/master/docs/linux/kernel_configs.md

To build guest kernel use the following:
```
cd build
make guest-kernel
```
This will download kernel sources, switch branch and apply config changes.
You will be asked for credentials to gitlab account.
Kernel config settings can be viewed/modified in guest-kernel Makefile target.

## Qemu
qemu Makefile target in build directory contains all steps needed to build
QEMU 4.2.0 from sources. For more details refer to it.

To build qemu run the following:
```
cd build
make qemu

```
## VM script
Before you start trying to run syzkaller, make sure VM is running with the above config.
If you are able to ssh to the VM from host you should be good to go.
```
./start-vm.sh &
sleep 60
./ssh-vm.sh
```

## Building syzkaller
Makefile in build directory will download syzkaller and go lang dependency to build syzkaller from sources.
Output directory is syzkaller/build/gopath/src/github.com/google/syzkaller/bin

```
cd build
make syzkaller
```

To remove syzkaller and dependencies just run make clean.

## Syzkaller config
Use my.cfg and change paths to the disk image and kernel locations.

## Qemu-wrapper
Make sure qemu-system-x86_64 is not in your PATH env variable.
apt install libexplain-dev
make qemu-wrapper
ln -s qemu-wrapper qemu-system-x86_64
export PATH=$(PWD):$PATH


## Syzkaller command line
./syz-manager -c my.cfg

This will pick your config file and start qemu-wrapper, which then
will change on the fly parameters passed by syzkaller to the qemu
and execve qemu-system-x86_64

## Debugging qemu-wrapper
If it fails to start fuzzing add -vv 10 -debug
This will show additional logs, which you can inspect.
If you enable DEBUG macro in qemu-wrapper it will create wrapper.log file which contains
list of all the parameters passed to the wrapped and parameters passed to the qemu.

You can also try to start a VM using by using test-wrapper.sh (modify paths accordingly).
It contains minimal set of parameters required by qemu-wrapper to start VM and similates
syzkaller call to the qemu-system-x86_64.
