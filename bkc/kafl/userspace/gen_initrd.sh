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
    echo "Fatal error: $1"
    echo
    exit 1
}

test -d "$TEMPLATE" || fatal "Could not find initrd template folder >>$TEMPLATE<<"

echo "[*] Installing latest busybox-static tools..."
sudo apt install busybox-static || fatal "Failed to install busybox?"
BUSYBOX=$(which busybox) || fatal "Could not find busybox binary."

TARGET="$(realpath $1)"
test -z "$TARGET" && fatal "Target folder $TARGET is a file. Refuse to overwrite."
test -f "$TARGET" && fatal "Target folder $TARGET is a file. Refuse to overwrite."
test -d "$TARGET" && fatal "Target folder $TARGET already exists. Refuse to overwrite."

mkdir -p "$TARGET" || fatal "Failed to create target folder $TARGET"

echo "[*] Populating target folder at $TARGET..."

cp -r $TEMPLATE/* "$TARGET"/
pushd "$TARGET" > /dev/null
	mkdir -p  bin dev  etc  lib  lib64  mnt/root  proc  root  sbin  sys  usr/bin
	$BUSYBOX --install -s bin/
	cp $BUSYBOX usr/bin
popd > /dev/null

echo "[*] Done. To generate the final initrd image, run $TARGET/build.sh <outputfile>"
