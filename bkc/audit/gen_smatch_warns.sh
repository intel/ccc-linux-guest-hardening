#!/bin/bash

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

# Quick helper to download smatch + generate a report

# Outputs smatch_warns.txt and filtered_smatch_warns.txt
# are stored to the target kernel folder (arg#1)

function fatal()
{
	echo $1
	echo "Usage: $(basename $0) <path/to/kernel>"
	exit
}

test -d "$BKC_ROOT" || fatal "Wrong or missing BKC_ROOT"
test -d $SMATCH_ROOT || fatal "Could not find smatch at $SMATCH_ROOT"

test "$#" -ne 1 && fatal "Need a single argument."
test "$1" == "-h" && fatal

KERNEL_ROOT=$1

test -d "$KERNEL_ROOT" || fatal "Wrong or missing kernel dir $KERNEL_ROOT"
test -d "$KERNEL_ROOT/scripts" || fatal "Wrong or missing kernel dir $KERNEL_ROOT"

if test ! -x $SMATCH_ROOT/smatch; then
	echo "[*] Could not find smatch. Attempting to build..."
	sudo apt install libsqlite3-dev
	make -C $SMATCH_ROOT -j $(nproc)
fi

SMATCH_WARNS=smatch_warns.txt
SMATCH_RUNNER=$SMATCH_ROOT/smatch_scripts/test_kernel.sh
SMATCH_FILTER=$BKC_ROOT/bkc/audit/process_smatch_output.py
test -f $SMATCH_RUNNER || fatal "Could not find $SMATCH_RUNNER"
test -f $SMATCH_FILTER || fatal "Could not find $SMATCH_FILTER"

if ! test -f $SMATCH_WARNS; then
	echo "[*] Building kernel for smatch analysis... (make -j$(nproc))"
	echo "    Press ctrl-c to cancel or any key to continue.."
	read
	pushd $KERNEL_ROOT
		$SMATCH_RUNNER
		python3 $SMATCH_FILTER $SMATCH_WARNS
	popd
fi

if test -f $KERNEL_ROOT/$SMATCH_WARNS; then
	echo "[*] Done - smatch report written to $KERNEL_ROOT/$SMATCH_WARNS"
else
	echo "[!] Error - failed to generate smatch report!"
fi
