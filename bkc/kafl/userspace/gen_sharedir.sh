#!/bin/bash

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#

# Generate a base sharedir for use with kAFL
# First argument is the target sharedir folder to be created + populated
#

HTOOLS_ROOT=$PACKER_ROOT/packer/linux_x86_64-userspace/
TEMPLATE=$BKC_ROOT/bkc/kafl/userspace/initrd_template
SHAREDIR=$BKC_ROOT/bkc/kafl/userspace/sharedir_template

fatal() {
	echo
    echo "Fatal error: $1"
    echo
    echo "Usage:"
    echo "   $0 <sharedir>"
    exit 1
}

test -n "$1" || fatal "Please provide a target folder."
TARGET=$(realpath $1)

test -x "$TARGET" && fatal "Target directory >>$TARGET<< already exists."

echo "[*] Building kAFL / htools..."
make -C $HTOOLS_ROOT bin64 || fatal "Failed to build kAFL htools?"

echo "[*] Populating sharedir..."
mkdir -p $TARGET
cp -v $SHAREDIR/* $TARGET/ || fatal "Failed copying sharedir template files!"
cp -v $HTOOLS_ROOT/bin64/* $TARGET/ || fatal "Failed copying htools"


echo "[*] Done. Customize sharedir startup via $TARGET/init.sh"
