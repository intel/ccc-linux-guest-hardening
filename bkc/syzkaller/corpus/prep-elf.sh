#!/bin/bash

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

SYZKALLER_BIN=../build/gopath/src/github.com/google/syzkaller/bin/
PROG2C=$SYZKALLER_BIN/syz-prog2c
UNPACKED_CORPUS=ve #unpacked corpus files
ELF=elf

if [ ! -f $PROG2C ]
then
	echo "Syzkaller prog2c does not exist ($PROG2C)"
	exit
fi

mkdir -p $ELF 2>/dev/null
files=`ls -1 $UNPACKED_CORPUS | wc -l`
progress=1

for file in `ls -1 $UNPACKED_CORPUS`;
do
	echo "Processing $progress/$files: $file"
	$PROG2C -prog $UNPACKED_CORPUS/$file  -repeat=1 -enable=none 2>/dev/null | gcc -x c -o  $ELF/$file.elf - 2>/dev/null
	progress=$((progress+1))
done
echo ""
actual=`ls -1 $ELF | wc -l`
echo Prepared $actual ELF binaries in $ELF directory!
