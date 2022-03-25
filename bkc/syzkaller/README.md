# TDX: Running syzkaller + with Qemu

## Install

The following components are needed to use syzkaller:

 - Go compiler and syzkaller itself
 - C compiler with coverage support
 - Linux kernel with coverage additions
 - Virtual machine or a physical device
If you encounter any troubles, check the [troubleshooting](https://github.com/google/syzkaller/blob/master/docs/troubleshooting.md) page.


## Host OS:
Recommended OS is Ubuntu 20.04, mostly because it contains GCC 9 and our host kernel
doesn't contain patches which enabled GCC 10+ (will not boot and compile without additional patches).


## Host Kernel:
For a more complete explanation of where to obtain and how to build the kernel for the host see the section [Install TDX SDV + kAFL host kernel]{https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/kafl#2-install-tdx-sdv--kafl-host-kernel} in the kafl documentation. The easiest way is to download the newest kernel .deb package [here]{https://github.com/IntelLabs/kafl.linux/releases/tag/kafl%2Fsdv-5.6-rc1} and install it as follows 
```
sudo dpkg -i /path/to/linux-image-*deb
```

Install kernel .deb package, then reboot. When GRUB comes up select advanced boot options, then select the kernel version you just installed.


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
We recommend using the precompiled package available here [TDVF-SDV v0.1](https://github.com/IntelLabs/kafl.edk2/releases/tag/tdvf-sdv-v0.1)

See the example in the kafl documentation [here](https://github.com/IntelLabs/kafl.edk2/releases/tag/tdvf-sdv-v0.1) for a guide on how to build it yourself. 

## Guest Kernel
Currently syzkaller uses tdx/fuzz-13 branch + guest.config,
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

### Go and syzkaller

`syzkaller` is written in [Go](https://golang.org), and `Go 1.16+` toolchain is required for build.
Generally we aim at supporting 2 latest releases of Go.
The toolchain can be installed with:

```
wget https://dl.google.com/go/go1.17.6.linux-amd64.tar.gz
tar -xf go1.17.6.linux-amd64.tar.gz
export GOROOT=`pwd`/go
export PATH=$GOROOT/bin:$PATH
```

See [Go: Download and install](https://golang.org/doc/install) for other options.

To download and build `syzkaller`:

``` bash
git clone https://github.com/google/syzkaller
cd syzkaller
make
```
After which all binaries should be appear in the folder `bin/`

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


### Troubleshooting

* QEMU requires root for `-enable-kvm`.

    Solution: add your user to the `kvm` group (`sudo usermod -a -G kvm` and relogin).

* QEMU crashes with:

    ```
    qemu-system-x86_64: error: failed to set MSR 0x48b to 0x159ff00000000
    qemu-system-x86_64: /build/qemu-EmNSP4/qemu-4.2/target/i386/kvm.c:2947: kvm_put_msrs: Assertion `ret == cpu->kvm_msr_buf->nmsrs' failed.
   ```

    Solution: remove `-cpu host,migratable=off` from the QEMU command line. The easiest way to do that is to set `qemu_args` to `-enable-kvm` in the `syz-manager` config file.