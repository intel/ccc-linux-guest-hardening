#!/bin/bash

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

#
# Launcher for TDX/kAFL fuzzing + diagnostics
# 

set -e
set -o pipefail

BIOS_IMAGE=$BKC_ROOT/TDVF.fd
INITRD_IMAGE=$BKC_ROOT/initrd.cpio.gz
DEFAULT_SHARE_DIR=$BKC_ROOT/sharedir
DEFAULT_WORK_DIR=$KAFL_WORKDIR
#DISK_IMAGE=$BKC_ROOT/tdx_overlay1.qcow2

# limited to 1G due to hardcoded TdHobList in TDVF!
MEMSIZE=1024

KAFL_FULL_OPTS="--redqueen --redqueen-hammer --redqueen-simple --grimoire --radamsa -p 2"
KAFL_QUICK_OPTS="--redqueen --redqueen-simple -D -p 2"

# useful for KPROBE-based harnesses
KERNEL_BUILD_PARAMS="KCFLAGS=-fno-ipa-sra -fno-ipa-cp-clone -fno-ipa-cp"

# enable TDX workaround in Qemu
export QEMU_BIOS_IN_RAM=1

# prefer $PWD/sharedir over $BKC_ROOT/sharedir
if test -d ./sharedir; then
	SHARE_DIR=$PWD/sharedir
else
	SHARE_DIR=$DEFAULT_SHARE_DIR
fi

# virtfs needs some default folder to serve to guest
test -d /tmp/kafl || mkdir /tmp/kafl

function usage()
{
	test -n "$1" && echo -e "\n$1" >&2
	cat >&2 << HERE

Usage: $0 <cmd> <dir> [args]

Available commands <cmd>:
  run    <target> [args]  - launch fuzzer with optional kAFL args [args]
  single <target> <file>  - execute target from <dir> with single input from <file>
  debug  <target> <file>  - launch target with single input <file>
                            and wait for gdb connection (qemu -s -S)
  cov <workdir>           - re-execute all payloads from <workdir>/corpus/ and
                            collect the individual trace logs to <workdir>/trace/
  smatch <workdir>        - get addr2line and smatch_match results from traces

  build <dir> <build>     - use harness config at <dir> to build kernel at <build>
  audit <dir> <config>    - smatch-audit guest-kernel using <config> and store to <dir>

<target> is a folder with vmlinux, System.map and bzImage
<workdir> is the output of a prior fuzzing run (default: $DEFAULT_WORK_DIR).

On 'run', the target files are copied to <workdir>/target for later diagnostics.
HERE
	exit
}

function fatal()
{
	echo -e "\nError: $@\n" >&2
	exit
}

function get_addr_lower
{
	echo "0x$(grep $1 $TARGET_MAP|head -1|cut -b -13)000"
}

function get_addr_upper
{
	printf "0x%x\n" $(( $(get_addr_lower $1) + 0x1000))
}

# arg1 is the System.map
function get_ip_regions
{
	# tracing is sensitive to size, padding, runtime rewrites..
	ip0_name="text"
	ip0_a=$(get_addr_lower _stext)
	ip0_b=$(get_addr_upper _etext)
	#ip0_b=$(get_addr_upper __entry_text_end)

	ip1_name="inittext"
	ip1_a=$(get_addr_lower _sinittext)
	ip1_b=$(get_addr_upper _einittext)
	#ip1_b=$(get_addr_upper __irf_end)

	ip2_name="drivers(??)"
	ip2_a=$(get_addr_lower early_dynamic_pgts)
	ip2_b=$(get_addr_lower __bss_start)
	#ip1_b=$(get_addr_lower __bss_start)
}

function set_workdir()
{
	test "$#" -ge 1 || usage "Error: Need additional <target> or <workdir> argument."
	TARGET_ROOT="$(realpath -e -- "$1")"

	# check if TARGET_ROOT is a valid <target> or <workdir>
	test -d "$TARGET_ROOT" || fatal "Argument '$1' is not a valid directory!"
	if [ -f $TARGET_ROOT/bzImage ]; then
		TARGET_BIN=$TARGET_ROOT/bzImage
		TARGET_MAP=$TARGET_ROOT/System.map
		TARGET_ELF=$TARGET_ROOT/vmlinux
		WORK_DIR=$DEFAULT_WORK_DIR
	elif [ -f $TARGET_ROOT/arch/x86/boot/bzImage ]; then
		TARGET_BIN=$TARGET_ROOT/arch/x86/boot/bzImage
		TARGET_MAP=$TARGET_ROOT/System.map
		TARGET_ELF=$TARGET_ROOT/vmlinux
		WORK_DIR=$DEFAULT_WORK_DIR
	elif [ -f $TARGET_ROOT/target/bzImage ]; then
		TARGET_BIN=$TARGET_ROOT/target/bzImage
		TARGET_MAP=$TARGET_ROOT/target/System.map
		TARGET_ELF=$TARGET_ROOT/target/vmlinux
		WORK_DIR=$TARGET_ROOT
	fi
	
	test -d "$TARGET_ROOT" || fatal "Invalid folder $TARGET_ROOT"
	test -f "$TARGET_BIN" || fatal "Could not find bzImage in $TARGET_ROOT or $TARGET_ROOT/target/"
	test -f "$TARGET_ELF" || fatal "Could not find vmlinux in $TARGET_ROOT or $TARGET_ROOT/target/"
	test -f "$TARGET_MAP" || fatal "Could not find System.map in $TARGET_ROOT or $TARGET_ROOT/target/"
}

# regular fuzz run based on TARGET_ROOT and default WORK_DIR
function run()
{
	get_ip_regions

	echo "PT trace regions:"
	echo "$ip0_a-$ip0_b ($ip0_name)"
	echo "$ip1_a-$ip1_b ($ip1_name)"
	echo "$ip2_a-$ip2_b ($ip2_name) // disabled"

	# failsafe: make sure we only delete fuzzer workdirs!
	test -d $WORK_DIR/corpus && rm -rf $WORK_DIR

	## record current setup and TARGET_ROOT/ assets to WORK_DIR/target/
	mkdir -p $WORK_DIR/target || fatal "Could not create folder $WORK_DIR/target"
	date > $WORK_DIR/target/timestamp.log
	cp $TARGET_BIN $TARGET_MAP $TARGET_ELF $WORK_DIR/target/
	cp $TARGET_BIN $TARGET_MAP $TARGET_ELF $WORK_DIR/target/
	echo "kAFL options: -m $MEMSIZE -ip0 $ip0_a-$ip0_b -ip1 $ip1_a-$ip1_b $KAFL_OPTS $*" > $WORK_DIR/target/kafl_args.txt

	## collect some more detailed target-specific info to help reproduce
	echo "Collecting target info from ${TARGET_ROOT}.."
	pushd $TARGET_ROOT > /dev/null
		cp .config $WORK_DIR/target/config
		test -f smatch_warns.txt && cp smatch_warns.txt $WORK_DIR/target/smatch_warns.txt
		if git status > /dev/null; then
			git log --pretty=oneline -4 > $WORK_DIR/target/repo_log
			git diff > $WORK_DIR/target/repo_diff
		fi
	popd  > /dev/null

	echo "Launching kAFL with workdir ${WORK_DIR}.."
	kafl_fuzz.py \
		--memory $MEMSIZE \
		-ip0 $ip0_a-$ip0_b \
		-ip1 $ip1_a-$ip1_b \
		--bios $BIOS_IMAGE \
		--initrd $INITRD_IMAGE \
		--kernel $TARGET_BIN \
		--work-dir $WORK_DIR \
		--sharedir $SHARE_DIR \
		$KAFL_OPTS "$@"
}

function debug()
{
	TARGET_PAYLOAD="$1"
	shift || fatal "Missing argument <file>"
	test -f "$TARGET_PAYLOAD" || fatal "Provided <file> is not a regular file: $TARGET_PAYLOAD"

	echo -e "\033[33m"
	echo "Resume from workdir: $WORK_DIR"
	echo "Target kernel location:  $TARGET_BIN"
	echo -e "\033[00m"

	kafl_debug.py \
		--resume --memory $MEMSIZE \
		--bios $BIOS_IMAGE \
		--initrd $INITRD_IMAGE \
		--kernel $TARGET_BIN \
		--work-dir $WORK_DIR \
		--sharedir $SHARE_DIR \
		--action gdb --input $TARGET_PAYLOAD "$@"
}

function single()
{
	TARGET_PAYLOAD="$1"
	shift || fatal "Missing argument <file>"
	test -f "$TARGET_PAYLOAD" || fatal "Provided <file> is not a regular file: $TARGET_PAYLOAD"

	echo "Executing $TARGET_PAYLOAD"

	get_ip_regions

	kafl_debug.py \
		--resume --memory $MEMSIZE \
		-ip0 $ip0_a-$ip0_b \
		-ip1 $ip1_a-$ip1_b \
		--bios $BIOS_IMAGE \
		--initrd $INITRD_IMAGE \
		--kernel $TARGET_BIN \
		--work-dir $WORK_DIR \
		--sharedir $SHARE_DIR \
		--log-hprintf \
		--action single -n 1 --input $TARGET_PAYLOAD "$@"

	LOG_SRC="$WORK_DIR/hprintf_1337.log"
	LOG_DST="$WORK_DIR/logs/$(basename "$TARGET_PAYLOAD")_printk.log"
	test -f "$LOG_SRC" && mv --backup=t "$LOG_SRC" "$LOG_DST" || echo "Failed to move log for $TARGET_PAYLOAD?"
}

function triage()
{
	TARGET_PAYLOAD="$1"
	shift || fatal "Missing argument <file>"
	test -f "$TARGET_PAYLOAD" || fatal "Provided <file> is not a regular file: $TARGET_PAYLOAD"

	echo -e "\033[33m"
	echo "Resume from workdir: $WORK_DIR"
	echo "Target kernel location:  $TARGET_BIN"
	echo "Target payload: $TARGET_PAYLOAD"
	echo -e "\033[00m"

	get_ip_regions

	kafl_debug.py \
		--resume --memory $MEMSIZE \
		-ip0 $ip0_a-$ip0_b \
		-ip1 $ip1_a-$ip1_b \
		--bios $BIOS_IMAGE \
		--initrd $INITRD_IMAGE \
		--kernel $TARGET_BIN \
		--work-dir $WORK_DIR \
		--sharedir $SHARE_DIR \
		--action triage --input $TARGET_PAYLOAD "$@"
}

function noise()
{
	TARGET_PAYLOAD="$1"
	shift || fatal "Missing argument <file>"
	test -f "$TARGET_PAYLOAD" || fatal "Provided <file> is not a regular file: $TARGET_PAYLOAD"


	get_ip_regions

	echo
	echo "Checking feedback noise on workdir '$WORK_DIR',"
	echo "Input: $TARGET_PAYLOAD"
	echo
	sleep 1

	kafl_debug.py \
		--resume --memory $MEMSIZE \
		-ip0 $ip0_a-$ip0_b \
		-ip1 $ip1_a-$ip1_b \
		--bios $BIOS_IMAGE \
		--initrd $INITRD_IMAGE \
		--kernel $TARGET_BIN \
		--work-dir $WORK_DIR \
		--sharedir $SHARE_DIR \
		--action noise -n 1000 --input $TARGET_PAYLOAD "$@"
}

function cov()
{
	echo
	echo "Collecting coverage on workdir '$WORK_DIR'"
	echo
	sleep 1

	get_ip_regions

	echo "PT trace regions:"
	echo "$ip0_a-$ip0_b ($ip0_name)"
	echo "$ip1_a-$ip1_b ($ip1_name)"
	echo "$ip2_a-$ip2_b ($ip2_name) // disabled"
	sleep 2

	kafl_cov.py \
		--resume --memory $MEMSIZE \
		-ip0 $ip0_a-$ip0_b \
		-ip1 $ip1_a-$ip1_b \
		--bios $BIOS_IMAGE \
		--initrd $INITRD_IMAGE \
		--kernel $TARGET_BIN \
		--work-dir $WORK_DIR \
		--sharedir $SHARE_DIR \
		--input $WORK_DIR --log-hprintf "$@"
}

function smatch_audit()
{
	test $# -eq 2 || usage "Wrong number of arguments"
	TARGET_DIR="$(realpath -e -- "$1")"; shift
	TARGET_CONFIG="$(realpath -e -- "$1")"; shift

	export KERNEL_BUILD_PARAMS
	$BKC_ROOT/bkc/audit/smatch_audit.sh $TARGET_DIR $TARGET_CONFIG
}

# build target from generated template config
function build_harness()
{
	test $# -eq 2 || usage "Wrong number of arguments"
	TEMPLATE_DIR="$(realpath -e -- "$1")"; shift
	BUILD_DIR="$(realpath -e -- "$1")"; shift

	test -f "$TEMPLATE_DIR/linux.template" || fatal "Could not find kernel template config in $TEMPLATE_DIR"
	test -f "$TEMPLATE_DIR/linux.config" || fatal "Could not find kernel harnes config in $TEMPLATE_DIR"

	test -d "$LINUX_GUEST" || fatal "Could not find kernel source tree at \$LINUX_GUEST"
	test -f "$LINUX_GUEST/Kconfig" || fatal "\$LINUX_GUEST is not pointing to a Linux source tree?"

	test -n "$MAKEFLAGS"   || echo "MAKEFLAGS is not set. Consider setting MAKEFLAGS=\"-j\$((2*\$(nproc)))\""

	cd $TEMPLATE_DIR
	test -d $BUILD_DIR || mkdir $BUILD_DIR
	cat linux.template linux.config > $BUILD_DIR/.config
	cd $LINUX_GUEST
	make mrproper
	make O=$BUILD_DIR olddefconfig
	make O=$BUILD_DIR "$KERNEL_BUILD_PARAMS"
}

function smatch_match()
{
	if test $USE_FAST_MATCHER -gt 0; then
		$BKC_ROOT/bkc/coverage/fast_matcher/target/release/fast_matcher -p $(nproc) -f -a -s $WORK_DIR/target/smatch_warns.txt $WORK_DIR > $WORK_DIR/traces/linecov.lst
		# Make paths relative
		$BKC_ROOT/bkc/coverage/strip_addr2line_absolute_path.sh $WORK_DIR/target/vmlinux $WORK_DIR/traces/linecov.lst
	else
		# match smatch report against line coverage reported in addr2line.lst
		SMATCH_OUTPUT=$WORK_DIR/traces/smatch_match.lst

		$BKC_ROOT/bkc/kafl/gen_addr2line.sh $WORK_DIR
		# Make paths relative
		$BKC_ROOT/bkc/coverage/strip_addr2line_absolute_path.sh $WORK_DIR/target/vmlinux $WORK_DIR/traces/addr2line.lst

		$BKC_ROOT/bkc/kafl/smatch_match.py $WORK_DIR |sort -u > $SMATCH_OUTPUT
		echo "Discovered smatch matches: $(wc -l $SMATCH_OUTPUT)"
	fi


	# search unknown callers...not really working yet..
	#$BKC_ROOT/kafl/trace_callers.py $WORK_DIR > $WORK_DIR/traces/io_callers.lst
}

test $# -ge 1 || usage "Error: Need a <cmd> argument."
ACTION="$1"; shift

[ "$ACTION" == "help" ] && usage
[ "$ACTION" == "--help" ] && usage
[ "$ACTION" == "-h" ] && usage

test -d "$BKC_ROOT" || fatal "Could not find BKC_ROOT. Check 'env.sh'."
test -d "$KAFL_ROOT" || fatal "Could not find KAFL_ROOT. Check 'env.sh'."

test -d $SHARE_DIR || mkdir -p $SHARE_DIR


# most actions require a workdir/target at $1
case $ACTION in
	full|run|cov|triage|single|debug|noise|smatch|ranges)
		set_workdir "$1"; shift
		;;
		*)
		;;
esac

case $ACTION in
	"audit")
		smatch_audit "$@"
		;;
	"build")
		build_harness "$@"
		;;
	"full")
		KAFL_OPTS=$KAFL_FULL_OPTS
		run "$@"
		;;
	"run")
		KAFL_OPTS=$KAFL_QUICK_OPTS
		run "$@"
		;;
	"single")
		single "$@"
		echo
		;;
	"triage")
		triage "$@"
		echo
		;;
	"debug")
		debug "$@"
		echo
		;;
	"cov")
		cov "$@"
		;;
	"smatch")
		smatch_match "$@"
		;;
	"noise")
		noise "$@"
		echo
		;;
	"ranges")
		get_ip_regions
		echo "PT trace regions:"
		echo -e "\tip0: $ip0_a-$ip0_b"
		echo -e "\tip1: $ip1_a-$ip1_b"
		;;
	*)
		usage "Error: Unrecognized command '$ACTION'."
		;;
esac
