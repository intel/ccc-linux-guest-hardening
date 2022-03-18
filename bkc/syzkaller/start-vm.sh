#!/bin/sh

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

SCRIPTDIR="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
BKC=$(realpath $SCRIPTDIR/..)

BIOS_IMAGE=$BKC/sdv/TDVF-acpitest-072120.fd
DISK_IMAGE=$BKC/syzkaller/build/image/stretch.img
KERNEL_IMAGE=$BKC/syzkaller/build/guest-kernel/arch/x86/boot/bzImage
QEMU=$BKC/syzkaller/build/qemu-4.2.0/build/x86_64-softmmu/qemu-system-x86_64
if [ ! -f "$DISK_IMAGE" ]; then
	echo "VM disk image does not exist ($DISK_IMAGE)"
	exit 1
fi
if [ ! -f "$BIOS_IMAGE" ]; then
	echo "BIOS image does not exist ($BIOS_IMAGE)"
	exit 1
fi
if [ ! -f "$KERNEL_IMAGE" ]; then
	echo "Guest kernel image does not exist ($KERNEL_IMAGE)"
	echo "Run: cd build && make guest-kernel"
fi
if [ ! -f "$QEMU" ]; then
	echo "Qemu binary does not exit ($QEMU)"
	echo "Run: cd build && make qemu"
fi

if [ -z "$VM_SSH_PORT"]; then
	VM_SSH_PORT=10322
fi

#set -x
QEMU_BIOS_IN_RAM=1 $QEMU \
    -monitor telnet:127.0.0.1:9091,server,nowait \
    -enable-kvm \
        -machine q35,accel=kvm,kernel_irqchip,sata=false,smbus=false \
    -s \
    -smp "4" \
    -snapshot \
    -bios $BIOS_IMAGE \
    -m "4G" \
    -cpu host,host-phys-bits,-la57 \
    -kernel "$KERNEL_IMAGE" \
    -nodefaults \
    -mon "chardev=stdio,mode=readline" \
    -drive id=drive0,file=$DISK_IMAGE,if=virtio \
    -device virtio-serial \
    -device virtconsole,chardev=stdio \
    -chardev "stdio,mux=on,id=stdio,signal=off" \
    -device isa-serial,chardev=stdio \
    -netdev user,id=mynet0,hostfwd=tcp::10322-:22,net=10.0.0.0/24,dhcpstart=10.0.0.50 \
    -device virtio-net-pci,netdev=mynet0 \
    -append "earlyprintk=ttyS0 console=hvc0 init=/sbin/init root=/dev/vda rw nokaslr tdx_wlist_devids=pci:0x8086:0x29c0,acpi:PNP0501 force_tdx_guest mitigations=off mce=off" \
        -no-reboot -nographic


