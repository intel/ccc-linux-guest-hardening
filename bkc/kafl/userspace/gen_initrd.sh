#!/bin/bash -e

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

# Helper script for generating busybox-based initrd rootfs
#
# Takes a single argument which is interpreted as the destination
# folder to be created and populated.
#

TEMPLATE=$BKC_ROOT/bkc/kafl/userspace/initrd_template

fatal() {
	echo
	echo -e "\nError: $@\n" >&2
	echo "Usage:\n\t$(basename $0) <path/to/initrd.cpio.gz>\n" >&2
	exit 1
}

test -d "$TEMPLATE" || fatal "Could not find initrd template folder >>$TEMPLATE<<"

echo "[*] Installing latest busybox-static tools..."
sudo apt install busybox-static || fatal "Failed to install busybox?"
BUSYBOX=$(which busybox) || fatal "Could not find busybox binary."

TARGET_INITRD="$(realpath $1)"
TARGET_ROOT="$(dirname "$TARGET_INITRD")/busybox-rootfs"

test -z "$TARGET_INITRD" && fatal "Output path $TARGET_INITRD is not set. Abort."
test -e "$TARGET_INITRD" && fatal "Target folder $TARGET_INITRD already exists. Abort."
test -e "$TARGET_ROOT"   && fatal "Target folder $TARGET_ROOT already exists. Abort."

mkdir -p "$TARGET_ROOT" || fatal "Failed to create busybox rootfs at $TARGET_ROOT"

echo "[*] Building busybox rootfs at $TARGET_ROOT..."

cp -r $TEMPLATE/* "$TARGET_ROOT"/
pushd "$TARGET_ROOT" > /dev/null
	mkdir -p  bin dev  etc  lib  lib64  mnt/root  proc  root  sbin  sys  usr/bin
	$BUSYBOX --install -s bin/
	cp $BUSYBOX usr/bin
popd > /dev/null

# bless and create final image
$BKC_ROOT/bkc/kafl/userspace/bless_initrd.sh "$TARGET_ROOT"
$TARGET_ROOT/build.sh "$TARGET_INITRD"
