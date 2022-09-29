#!/bin/bash

#
# Perform smatch analysis on linux kernel
#
# Cleans + builds the kernel at $LINUX_GUEST and copies smatch reports to provided target dir.
#

set -e
set -o pipefail

function usage()
{
	test -n "$1" && echo -e "\n$1" >&2
	cat >&2 << HERE

Usage: $0 <dir> <config>

Where:
  <target>  - output directory for storing smatch results
  <config>  - kernel config to be used in build/audit
HERE
	exit
}

function fail()
{
	echo -e "\nError: $@\n" >&2
	exit
}

# Simplified version of smatch/smatch_scripts/test_kernel.sh, without the -j override
analyze_kernel()
{
	test -n "$MAKEFLAGS" || echo "MAKEFLAGS is not set. Consider setting MAKEFLAGS=\"-j\$((2*\$(nproc)))\""
	TARGETS="${KERNEL_BUILD_TARGETS:="bzImage modules"}"
	PARAMS="${KERNEL_BUILD_PARAMS:=""}"

	echo "Analysing kernel at $LINUX_GUEST. This may take a minute.."
	cd $LINUX_GUEST
	make clean
	find -name \*.c.smatch -exec rm \{\} \;
	make -k CHECK="$SMATCH_BIN -p=kernel --file-output --succeed $*" C=1 "$PARAMS" $TARGETS 2>&1 | tee $SMATCH_LOG
	find -name \*.c.smatch -exec cat \{\} \; -exec rm \{\} \; > $SMATCH_WARNS
	find -name \*.c.smatch.sql -exec cat \{\} \; -exec rm \{\} \; > $SMATCH_WARNS.sql
	find -name \*.c.smatch.caller_info -exec cat \{\} \; -exec rm \{\} \; > $SMATCH_WARNS.caller_info

	# postprocess smatch report
	$SMATCH_FILTER --force -o $SMATCH_FILTERED $SMATCH_WARNS
	$SMATCH_TRANSFER --force -o $SMATCH_TRANSFERRED $SMATCH_ANNOTATED $SMATCH_FILTERED

	cp $SMATCH_WARNS $SMATCH_LOG $TARGET_DIR/
	cp $SMATCH_FILTERED $SMATCH_TRANSFERRED $TARGET_DIR/
}

# Helpers
SMATCH_BIN=$SMATCH_ROOT/smatch
SMATCH_RUNNER=$SMATCH_ROOT/smatch_scripts/test_kernel.sh
SMATCH_FILTER=$BKC_ROOT/bkc/audit/process_smatch_output.py
SMATCH_TRANSFER=$BKC_ROOT/bkc/audit/transfer_results.py

SMATCH_ANNOTATED=$BKC_ROOT/bkc/audit/sample_output/5.15-rc1/smatch_warns_5.15_tdx_allyesconfig_filtered_results_analyzed

# Outputs
SMATCH_LOGS=smatch_build.log
SMATCH_WARNS=smatch_warns.txt                 # raw generated smatch warnings (audit list)
SMATCH_FILTERED=smatch_warns_filtered.txt     # audit list filtered by relevant subsystems
SMATCH_TRANSFERRED=smatch_warns_annotated.txt # audit list annotated based on prior review

test -d "$BKC_ROOT"    || fail "Could not find \$BKC_ROOT - try to 'make env'."
test -d "$LINUX_GUEST" || fail "Could not find \$LINUX_ROOT - try to 'make env'."
test -d "$SMATCH_ROOT" || fail "Could not find \$SMATCH_ROOT - try to 'make deploy -- --tags smatch'"
test -f $SMATCH_BIN    || fail "Could not find $SMATCH_BIN - try to 'make deploy -- --tags smatch'"
test "$#" -eq 2        || usage "Bad or missing arguments"


TARGET_DIR="$(realpath -e -- "$1")"; shift
CONFIG_NEW="$(realpath -e -- "$1")"; shift
CONFIG_OLD="$LINUX_GUEST/.config"

# copy .config and backup existing file if needed
if test ! -f $CONFIG_OLD; then
	cp $CONFIG_NEW $CONFIG_OLD
else
	if test ! $CONFIG_NEW -ef $CONFIG_OLD; then
		CONFIG_BAK=`mktemp`
		cp $CONFIG_OLD $CONFIG_BAK
		cp $CONFIG_NEW $CONFIG_OLD
	fi
fi

analyze_kernel

# restore .config
if test -n "$CONFIG_BAK"; then
	cp $CONFIG_BAK $CONFIG_OLD
	rm $CONFIG_BAK
fi

exit 0
