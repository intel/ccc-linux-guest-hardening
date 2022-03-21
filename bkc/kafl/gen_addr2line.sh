#!/bin/bash
#
# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT
#
# Quick helper to get unique blocks and source file/line from kAFL traces
#
# Note that addr2line list generated from simple edge trace is slightly incomplete
#
# Set USE_GHIDRA=1 to generate the complete dump of covered addresses and
# corresponding larger (and very redundant) addr2line list. (slow)

set -e

USE_GHIDRA="${USE_GHIDRA:-0}"
	
KAFL_ROOT=$(west list -f {abspath} kafl)
KAFL_TOOLS=$(realpath $KAFL_ROOT/scripts/)


function fatal()
{
	echo $1
	echo "Usage: $(basename $0) <path/to/work_dir>"
	exit
}

which eu-addr2line || fatal "Error: Could not fine eu-addr2line...exit.."

INPUT=$1; shift || fatal ""
if [ -d $INPUT ]; then
	WORK_DIR=$(realpath $INPUT)
	EDGE_LIST=$WORK_DIR/traces/edges_uniq.lst
	BLOCK_LIST=$WORK_DIR/traces/blocks_uniq.lst
	ADDR_LIST=$WORK_DIR/traces/addr_uniq.lst
	LINES_LIST=$WORK_DIR/traces/addr2line.lst
	test -f $EDGE_LIST || fatal "Error: Supplied workdir is missing coverage info at $EDGE_LIST"
elif [ -f $INPUT ]; then
	EDGE_LIST=$(echo $INPUT|sed s/.lz4$/\.edges.lst/)
	BLOCK_LIST=$(echo $INPUT|sed s/.lz4$/\.blocks.lst/)
	ADDR_LIST=$(echo $INPUT|sed s/.lz4$/\.addr.lst/)
	LINES_LIST=$(echo $INPUT|sed s/.lz4$/\.addr.lst/)
	lz4cat $INPUT > $EDGE_LIST || fatal "Error: Expected lz4-compressed trace at $INPUT"
else
	fatal "Error: Expected first argument to be target workdir or lz4 payload trace."
fi

test -f $LINES_LIST && echo "Output $LINES_LIST already exists. Skipping.." && exit

TARGET_ELF=$WORK_DIR/target/vmlinux
test -f $TARGET_ELF || fatal "Could not find $TARGET_ELF in provided workdir.."

echo "Using unique edges from $EDGE_LIST"

if [ -d $INPUT ]; then
	sed -e 's/\,/\n/' -e 's/\,.*$//' $EDGE_LIST|sort |uniq > $BLOCK_LIST
else
	sed -e 's/\,/\n/' -e 's/\,.*$//' $EDGE_LIST > $BLOCK_LIST
fi
echo "Unique blocks found: $(wc -l $BLOCK_LIST)"


if test $USE_GHIDRA -gt 0  && test ! -f $ADDR_LIST; then
	echo "Using Ghidra to generate complete list of seen code locations.."

	GHIDRA_DUMP_LOG=$WORK_DIR/traces/ghidra_dump.log
	REACHED_LOG=$WORK_DIR/traces/reached_addrs.lst

	$KAFL_TOOLS/ghidra_run.sh $WORK_DIR $TARGET_ELF $KAFL_TOOLS/ghidra_dump_blocks.py > $GHIDRA_DUMP_LOG 2>&1
	#grep ERROR $GHIDRA_DUMP_LOG && fatal "Ghidra run failed, please check $GHIDRA_DUMP_LOG"
	grep reached $GHIDRA_DUMP_LOG |sed -e 's/reached: //' -e 's/\ .*//'  > $ADDR_LIST

	echo "Identified visited code locations: $(wc -l $ADDR_LIST)"
fi

echo "Generating addr2line dump for seen code locations.."
test -f $ADDR_LIST || ADDR_LIST=$BLOCK_LIST
eu-addr2line --pretty-print -afi -e $TARGET_ELF < $ADDR_LIST > $LINES_LIST

echo "Generated addr2line table: $(wc -l $LINES_LIST)"
