#!/bin/bash -e

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

# Helper script for generating buildroot-based initrd rootfs for userspace fuzzing

set -e

BUILDROOT_VERSION="buildroot-2021.11"
URL="https://buildroot.org/downloads/$BUILDROOT_VERSION.tar.gz"

function fatal()
{
	echo -e "\nError: $@\n" >&2
	echo -e "Usage:\n\t$(basename $0) <path/to/initrd.cpio.gz>\n" >&2
	exit
}

test -n "$BKC_ROOT" || fatal "BKC_ROOT is not set. Try 'make env'"
test $# -eq 1 || fatal "Missing argument."

TARGET_INITRD="$(realpath "$1")"

if test -d "$BUILDROOT_VERSION" -a -f $TARGET_INITRD; then
   echo "Output files already exist. Skipping.."
   exit 0
fi

# cleanup
rm -rf $BUILDROOT_VERSION $BUILDROOT_VERSION.tgz

wget -O $BUILDROOT_VERSION.tgz "$URL"
tar xzf $BUILDROOT_VERSION.tgz
rm $BUILDROOT_VERSION.tgz
cd $BUILDROOT_VERSION

git init .; git add .; git commit -m "vanilla $BUILDROOT_VERSION"
git am $BKC_ROOT/bkc/kafl/userspace/buildroot/0001-upgrade-to-stress-ng-0.13.05.patch
git am $BKC_ROOT/bkc/kafl/userspace/buildroot/0002-new-package-perf_fuzzer.patch

cp $BKC_ROOT/bkc/kafl/userspace/buildroot/buildroot.config .config
cp $BKC_ROOT/bkc/kafl/userspace/buildroot/busybox.config package/busybox/.config

make source
make # set jobs via MAKEFLAGS

# bless and re-make final image
$BKC_ROOT/bkc/kafl/userspace/bless_initrd.sh output/target/
make
ln -sf $(realpath output/images/rootfs.cpio.gz) $TARGET_INITRD
