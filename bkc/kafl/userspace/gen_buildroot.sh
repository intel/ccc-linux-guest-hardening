#!/bin/bash -e

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

# Helper script for generating buildroot-based initrd rootfs for userspace fuzzing

BUILDROOT_VERSION="buildroot-2021.11"
URL="https://buildroot.org/downloads/$BUILDROOT_VERSION.tar.gz"

if [[ -z "${BKC_ROOT}" ]]; then
	echo "BKC_ROOT is not set. Please do `make env`"
	exit 1
fi

cd $BKC_ROOT
wget $URL
tar xzf $(basename $URL)
rm $BUILDROOT_VERSION.tar.gz
cd $BUILDROOT_VERSION
git init .; git add .; git commit -m "vanilla $BUILDROOT_VERSION"
git am $BKC_ROOT/bkc/kafl/userspace/buildroot/0001-upgrade-to-stress-ng-0.13.05.patch
git am $BKC_ROOT/bkc/kafl/userspace/buildroot/0002-new-package-perf_fuzzer.patch
cp $BKC_ROOT/bkc/kafl/userspace/buildroot/buildroot.config .config
cp $BKC_ROOT/bkc/kafl/userspace/buildroot/busybox.config package/busybox/.config
make source
make -j $(nproc)
cd $BKC_ROOT
$BKC_ROOT/bkc/kafl/userspace/bless_initrd.sh $BUILDROOT_VERSION/output/target/
make -C $BUILDROOT_VERSION
ln -sf  $BUILDROOT_VERSION/output/images/rootfs.cpio.gz $BKC_ROOT/initrd.cpio.gz

