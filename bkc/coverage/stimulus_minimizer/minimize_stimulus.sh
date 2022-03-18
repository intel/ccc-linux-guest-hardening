#!/bin/bash

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#

#
# Process trace+gcov outputs produced by kAFL user stimulus runner
#
# Find unique stack backtraces from trace log
# For any output with not yet seen backtrace, compute gcov + smatch match
#
# Input: kAFL workdir/dump folder containing gcov+trace archives
#
# Output: Several files in target folder:
# - seen/* - individual seen stack traces, named by their sha1sum
# - repo/unique_rips - stack hashes that triggered gcov for here
# - repo/smatch_match.lst - overlap of smatch match and gcovr.lst
#
# Note: Do not run this in parallel, the underlying gcov will overwrite
# its peer's files $LINUX_BUILD_ROOT
#

LINUX_BUILD_ROOT=/home/$USER/tdx/linux-guest
SMATCH_WARNS=$LINUX_BUILD_ROOT/filtered_smatch_warns

# number of levels to consider for reduced 'short' stack
SHORT_STACKLEVELS=5

COV2ADDR=/home/$USER/tdx/bkc/kafl/userspace/coveralls2addr.py
GCOVR=$(which gcovr)

function fatal
{
	echo
	echo $1
	echo
	exit 1
}

test -x $GCOVR || fatal "Need gcovr. Try pip3 install gcovr."
test -x $COV2ADDR || fatal "Could not find $COV2ADDR"
test -d $1 || fatal "Provided workdir is invalid."
test -f $LINUX_BUILD_ROOT/arch/x86/kernel/tdx.c || fatal "Could not find TDX kernel source tree"

DUMP_DIR="$(realpath $1)/dump"
test -d $DUMP_DIR || fatal "Provided workdir is invalid or has no dump/ folder."

pushd $DUMP_DIR > /dev/null
	grep -h "^Payload in:"  ../hprintf_*log|sort -u |sed "s/^Payload in: //" > payloads_in.lst
	grep -h "^Payload out:"  ../hprintf_*log|sort -u |sed "s/^Payload out: //" > payloads_out.lst
	wc -l payloads_in.lst
	wc -l payloads_out.lst
popd > /dev/null


pushd $DUMP_DIR

	FULL_SEEN="full_stacks"
	SHORT_SEEN="short_stacks"
	mkdir $FULL_SEEN
	mkdir $SHORT_SEEN
	
	for tgz in $DUMP_DIR/*.tar.gz; do
		name="$(basename "$tgz"|sed s/.tar.gz//)"
		tracedir="$(dirname "$tgz")/$name"
		HAVE_NEW_STACKS=false

		test -r "$tgz" || fatal "Could not find: $tgz"
		#test -d "$tracedir" && rm -rf "$tracedir"
		test -d "$tracedir" && continue
		mkdir -p "$tracedir" || fatal "erorr creating $tracedir for $name"

		#pushd "$tracedir" > /dev/null

		echo "[*] Processing $tgz"
		tar xzf "$tgz" -C $tracedir --strip-components=1

		# extract stacks from trace and build a hash map
		csplit -q --prefix="$tracedir/csplit_" -b "%04d" $tracedir/trace '/tdx_fuzz: rip/' '{*}'
		echo " => Filtering $(ls "$tracedir"/csplit_*|wc -l|awk '{print $1}') trace stacks.."
		for stack in "$tracedir"/csplit_*; do
			
			# abort on empty stack (trace header)
			if ! grep -q "^ => " "$stack"; then
				rm $stack
				continue
			fi

			# unique stack hash
			sha1=$(grep "^ => " "$stack"|sha1sum|cut -b -40)

			# compressed stack hash (reduced size => less noise)
			if $(grep -q asm_exc_virtualization_exception $stack); then
				short_sha1=$(grep -A $SHORT_STACKLEVELS asm_exc_virt $stack|sha1sum|cut -b -40)
			else
				short_sha1=$(grep -A $SHORT_STACKLEVELS 'tdg_fuzz$' $stack|sha1sum|cut -b -40)
			fi

			test -z "$sha1" && fatal "bad sha $sha1 for $name"
			test -z "$short_sha1" && fatal "bad short_sha $short_sha1 for $name"

			# create a few maps for later processing/sorting of best payloads
			test -d $tracedir/full_stacks || mkdir $tracedir/full_stacks
			test -d $tracedir/short_stacks || mkdir $tracedir/short_stacks

			# global map of full stacks
			if ! test -d $FULL_SEEN/$sha1; then
				mkdir $FULL_SEEN/$sha1
				mv $stack $FULL_SEEN/$sha1/stack.txt
			else
				rm $stack
			fi

			# global map of short stacks + local 'unique' short stack map
			if ! test -d $SHORT_SEEN/$short_sha1; then
				mkdir $SHORT_SEEN/$short_sha1
				test -d $tracedir/new_short_stacks || mkdir $tracedir/new_short_stacks
				ln -Ts ../$SHORT_SEEN/$short_sha1 $tracedir/new_short_stacks/$short_sha1
				HAVE_NEW_STACKS=true
			fi

			# local reference of seen full + short stacks to global stacks
			ln -Tsf ../../$FULL_SEEN/$sha1        $tracedir/full_stacks/$sha1
			ln -Tsf ../../$SHORT_SEEN/$short_sha1 $tracedir/short_stacks/$short_sha1
			
			# build a list so we can tell how often stack was called
			echo "$name" >> "$FULL_SEEN/$sha1/callers.lst"
			ln -Tsf "../../$name" "$FULL_SEEN/$sha1/caller_$name"
			
			# also reference calling payload from global short or full stack lists
			echo "$name" >> "$SHORT_SEEN/$short_sha1/callers.lst"
			ln -Tsf "../../$name" "$SHORT_SEEN/$short_sha1/caller_$name"
			ln -Tsf "../../$FULL_SEEN/$sha1" "$SHORT_SEEN/$short_sha1/full_stack_$sha1"
		done

		pushd $tracedir > /dev/null
		if $HAVE_NEW_STACKS; then
			echo " => Processing coverage.."
			GCDA_ROOT=$tracedir/$LINUX_BUILD_ROOT
			test -d "$GCDA_ROOT" || echo No GCDA root found, exit..
			test -d "$GCDA_ROOT" || exit
			$GCOVR -j 16 --txt gcovr.txt --coveralls gcovr.json --coveralls-pretty -r $LINUX_BUILD_ROOT $GCDA_ROOT
			$COV2ADDR > gcovr.lst

			SMATCH_REPORT=${tracedir}_smatch_match.lst
			SMATCH_SLOCS="$(grep "^[a-z]" "$SMATCH_WARNS"|cut -d " " -f 1)"
			for sloc in $SMATCH_SLOCS; do
				grep -w $sloc gcovr.lst
			done > $SMATCH_REPORT

			if test -s $SMATCH_REPORT; then
				echo " => New smatch report: $(wc -l $SMATCH_REPORT)"
			else
				echo " => Warning: trace hits without smatch matches in $name"
				mv $SMATCH_REPORT ${tracedir}_smatch_EMPTY.lst
			fi
		fi

		# cleanup - zip any big + non-essential files
		GCOV_DIR=$(echo $LINUX_BUILD_ROOT|sed -e 's/\///' -e 's/\/.*//')
		test -d ./$GCOV_DIR || fatal "Error in gcov cleanup - abort!"
		tar -czf gcov.tgz $GCOV_DIR && rm -rf ./$GCOV_DIR
		test -f gcovr.json && gzip gcovr.json
		test -f gcovr.txt && gzip gcovr.txt

		popd > /dev/null
	done

	for stack in short_stacks/*; do
		echo "stack: $stack"
		sort $stack/callers.lst|uniq -c|sort -nr|head -4
	done > $DUMP_DIR/top_payloads.lst

	echo -e "\nTotal smatch matches:"
	wc -l $DUMP_DIR/*_smatch_match.lst

	echo -e "\nUnique smatch matches:"
	awk '{print $2}' $DUMP_DIR/*_smatch_match.lst |sort -u > $DUMP_DIR/unique_smatch_match.lst
	wc -l $DUMP_DIR/unique_smatch_match.lst

popd > /dev/null

