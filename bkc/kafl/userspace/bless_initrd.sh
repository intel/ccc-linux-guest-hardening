#!/bin/bash

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

# Bless an initrd to initiate kAFL loader script.
#
# First argument is the path to the inird rootfs to be blessed.
#
# Blessing works by hooking /etc/rcS to initiate loader.sh.
# Loader uses hget to update + bootstrap everything via kAFL sharedir

HTOOLS_ROOT=$PACKER_ROOT/packer/linux_x86_64-userspace/
TEMPLATE=$BKC_ROOT/bkc/kafl/userspace/initrd_template
SHAREDIR=$BKC_ROOT/bkc/kafl/userspace/sharedir_template

fatal() {
	echo
    echo "Fatal error: $1"
    echo
    echo "Usage:"
    echo "   $0 <initrd_root>"
    exit 1
}

TARGET=$(realpath $1)
test -d $TARGET || fatal "Could not find target initrd folder at $TARGET"
test -d $TARGET/etc || fatal "Is the target folder really an initrd?"
test -x $TARGET/bin/sh || fatal "Is the target folder really an initrd?"
#test -d $TARGET/fuzz && fatal "Target initrd already seems to be blessed?"
#test -x $TARGET/loader.sh && fatal "Target initrd already seems to be blessed?"

echo "[*] Building kAFL / htools..."
make -C $HTOOLS_ROOT bin64 || fatal "Failed to build kAFL htools?"

pushd $TARGET > /dev/null

	echo "[*] Populating target rootfs..."
	cp $SHAREDIR/loader.sh ./ || fatal "Failed copying loader.sh"

	test -d fuzz || mkdir fuzz
	cp $HTOOLS_ROOT/bin64/{hget,hcat,habort} fuzz/ || fatal "Failed copying htools"

	chmod a+x loader.sh
	chmod a+x fuzz/*

	if ls etc/init.d/S0* > /dev/null 2>&1; then
		# works for buildroot and anything close to sysv init
		echo "[*] Adding loader.sh to /etc/init.d/ scripts.."
		ln -sf /loader.sh etc/init.d/S00loader
	elif ! test -e etc/rcS; then
		# homebrew initrd may not works for busybox initrd
		echo "[*] Linking etc/rcS to loader.sh.."
		ln -sf /loader.sh etc/rcS
	else
		echo "Not a sysv init and refuse to overwrite etc/rcS. Please ensure loader.sh is launched on boot."
	fi

popd > /dev/null

echo "[*] All done. You can inspect + build your initrd now!"
