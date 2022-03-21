#!/bin/bash

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

##
#
# ELF Stimulus Filtering
#
# Execute payloads one by one. Check the trace result and hpush if relevant.
# Also hprintf a message 'Payload <in|out> $identifier' for easy postprocessing of candidates.
#
# Complications:
#
# - May have *many* payloads, so download ELFs individually via payload.lst
#
# - Allow multiple execution modes depending on type of payload.lst: commands, ELFs, syzkaller-progs:
#PAYLOADS=<elfs.lst|progs.lst|cmds.lst>
PAYLOADS=progs.lst
PAYLOADS=ltp.lst
PAYLOADS=cmds.lst
#
# - We want to use kAFL snapshot to restore VM state after each execution. Need to
#   disable input fuzzing and not abort on end-of-payload, otherwise we may not
#   return to userspace and fail to upload/log results.
FUZZ_TDCALL="1"
EXIT_AT_EOF="1"
#
# - We cannot loop statefully while resetting the VM state on each run.
#   So drive execution externally based on first bytes of fuzz input.
#   In standard fuzzing mode this will cause multiple execution of whatever
#   the fuzzer finds interesting. Also this random sampling of the payload list
#   is quite inefficient. Proper solution is to use debug/cov style frontend.
#
#   Workaround: Set FILTER_EVENT=kasan to report 'out' payloads as KASAN.
FILTER_EVENT="kasan"
#
# - Since we are abusing the fuzzer here to sample the payload space, we want
#   to continue random sampling even when no coverage feedback is detected.
#   To do this, set kickstart = True in kAFL-Fuzzer/fuzzer/processes/slave.py
#
# Note: Tools in rootfs may have non-standard behavior, especially those based on busybox!
#
# Note: Caller pipes everything to hcat, but messages can be lost due to buffering + snapshot restore.
#       Redirect outputs directly to hcat to ensure they will be printed!
#
# Note: Remember to enable desired features on host Qemu as well as guest kernel config.
#       We can't trigger network-IO from userspace if Linux did not find any.
##

#set -x # set debug

function fatal
{
	echo "$1"|hcat
	exit 1
}

function fetch
{
	dest=$(basename $1)
	hget $1 /fuzz/$dest
	chmod a+x /fuzz/$dest
}

echo "[*] kAFL agent status:"

fetch habort
fetch hrange
fetch hcat
fetch hpanic
fetch hpush
fetch hget

fetch syz/syz-execprog
fetch syz/syz-executor

dmesg -c

mount -t debugfs none /sys/kernel/debug/
mount -t tracefs nodev /sys/kernel/tracing
mount -t cgroup2 none /sys/fs/cgroup

# stimulus tools should focus on this mount point!
#mount -t 9p -o trans=virtio tmp /mnt

# LTP is looking up modules.dep
depmod

# run DHCP once to init network
# only use if needed - causes background virtio activity
# running dhcp as part of fuzzing confuses Qemu?
#udhcpc 2>&1 |hcat
#wget http://10.0.2.2 2>&1 |hcat
#ping -c 3 10.0.2.2 2>&1 |hcat
#ping -c 1 10.0.2.3 2>&1 |hcat

echo "[*] kAFL agent status:"
KAFL_CTL=/sys/kernel/debug/kafl

grep . $KAFL_CTL/*
grep . $KAFL_CTL/status/*

echo "[*] ftrace status:"
TRACE_CTL=/sys/kernel/tracing
TRACE_EVENTS="tdx_fuzz"
#TRACE_EVENTS="tdg_virtualization_exception"
STACKTRACE_EVENTS="tdx_fuzz"
#TRACE_EVENTS=$(grep syscalls $TRACE_CTL/available_events|sed s/.*://)

echo "[*] GCOV status:"
GCOV_CTL=/sys/kernel/debug/gcov
GCOV_ROOT=""
ls -l $GCOV_CTL


function trace_reset
{
	echo 0 > $TRACE_CTL/tracing_on
	echo " " > $TRACE_CTL/trace
	echo " " > $TRACE_CTL/set_event

	#echo "$TRACE_EVENTS" |tee $TRACE_CTL/set_event
	for i in $TRACE_EVENTS; do
		echo 1 > $TRACE_CTL/events/syscalls/$i/enable
	done
	#for i in $STACKTRACE_EVENTS; do
	#	echo stacktrace > $TRACE_CTL/events/tdx/$i/trigger
	#done

	echo 1 > $TRACE_CTL/tracing_on
	echo " " > $TRACE_CTL/trace
}
		
function trace_push
{
	name="$(echo "$1"|tr -d '#;-'|tr '\/ ' _)"
	mkdir /trace
	cp $TRACE_CTL/trace /trace/trace
	echo "$1" > /trace/payload_id
	tar cf trace.tar /trace
	gzip trace.tar
	#hpush /tmp/trace.gz "trace_${name}_XXXXXX.gz"
	hpush /tmp/trace.gz "${name}.trace.gz"
}

function trace_info
{
	grep -H tdx $TRACE_CTL/available_events
	grep -H . $TRACE_CTL/set_event
	grep -H . $TRACE_CTL/tracing_on
	grep -H . $TRACE_CTL/trace
	echo "Events: $TRACE_EVENTS"
}

function gcov_push
{
	name="$(echo "$1"|tr -d '#;-'|tr '\/ ' _)"
	#qid=$(cat $KAFL_CTL/status/worker_id)

	if test -d $GCOV_CTL; then
		# direct tar doesn't work, use cp/cat
		cp -R $GCOV_CTL/$GCOV_ROOT /gcov
		echo "$1" > /gcov/payload_id
		tar cf gcov.tar /gcov
		gzip gcov.tar
		#hpush gcov.tar.gz "gcov_${name}_XXXXXX.tar.gz"
		hpush gcov.tar.gz "${name}.gcov.tar.gz"
	fi
}

function all_push
{
	name="$(echo "$1"|tr -d '#;-'|tr '\/ ' _)"
	#qid=$(cat $KAFL_CTL/status/worker_id)

	# filter by tdx_fuzz activity? - need fuzz_tdcall=Y!
	#if grep -v ^0 $KAFL_CTL/status/stats_*; then

	if test -d $GCOV_CTL; then
		# direct tar doesn't work, use cp/cat
		cp -R $GCOV_CTL/$GCOV_ROOT /trace
		rm /trace/reset
		cp $TRACE_CTL/trace /trace/trace
		echo "$1" > /trace/payload_id
		tar cf trace.tar /trace
		gzip trace.tar
		#hpush trace.tar.gz "trace_${name}_XXXXXX.tar.gz"
		hpush trace.tar.gz "trace_${name}.tar.gz"
	fi
}

function gcov_reset
{
	echo "1" > $GCOV_CTL/reset
}

function rand_select
{
	list=$1
	#RAND=$(cat /sys/kernel/debug/kafl/buf_get_u32)
	PNUM=$(wc -l < $list)
	NUM=$(expr 1 + $RAND % $PNUM)

	if ! test $NUM -ge 0; then
		fatal "NUM=$NUM is not an integer?"
	fi

	PNAME=$(sed "${NUM}q;d" $list)
	#echo "ELF $NUM ($RAND_NUM % $PNUM) $PNAME"

	echo "$PNAME"
}

test -d $KAFL_CTL || fatal "Could not find kAFL debugfs"
test -d $TRACE_CTL || fatal "Could not find tracefs"
test -d $GCOV || echo "GCOV not available"|hcat

trace_info|hcat

#echo "setcr3" > $KAFL_CTL/control
#echo "enable" > $KAFL_CTL/control
echo "start"  > $KAFL_CTL/control
echo $EXIT_AT_EOF > $KAFL_CTL/exit_at_eof
echo $FUZZ_TDCALL  > $KAFL_CTL/fuzz_tdcall
echo 1  > $KAFL_CTL/dump_callers

trace_reset
#gcov_reset

# Download payload lists and execute depending on type
fetch $PAYLOADS
RAND=$(cat /sys/kernel/debug/kafl/buf_get_u32)
#RAND=1

# if we don't load direclty from ltp.lst, offer to runltp via cmd.lst

#if test -d /usr/lib/ltp-testsuite; then
#	if ! test -f /fuzz/ltp.lst; then
#		#ls /usr/lib/ltp-testsuite/testcases/runtest/ |xargs -n 1 basename > /fuzz/ltp.lst
#		fetch ltp.lst
#		PATH=$PATH:/usr/lib/ltp-testsuite/
#	fi
#fi

if test -s /fuzz/elfs.lst; then
	PNAME=$(rand_select /fuzz/elfs.lst)
	TARGET=/fuzz/elf.elf
	hget "$PNAME" $TARGET
	chmod a+x $TARGET
	$TARGET
fi

if test -s /fuzz/ltp.lst; then
	LTPARGS=$(rand_select /fuzz/ltp.lst)
	if $(echo "$LTPARGS"|grep -q sleep); then
		PNAME="sleep 2"
		sleep 2
	else
		PNAME="ltp -d /tmp/ltp -t 3s -f $LTPARGS"
		/usr/lib/ltp-testsuite/runltp -d /tmp/ltp -t 3s -f $LTPARGS 2>&1 |hcat
	fi
fi

echo "init.sh starting cmd..."|hcat
if test -s /fuzz/cmds.lst; then
	PNAME=$(rand_select /fuzz/cmds.lst)
	if $(echo "$PNAME"|grep -q runltp); then
		# same rand but different modulus - use many runltp entries
		LTPTEST=$(rand_select /fuzz/ltp.lst)
		PNAME=$(echo $PNAME|sed s/LTPTEST/$LTPTEST/)
	fi
	PNAME=$(echo $PNAME|sed s/RANDINT/$RAND/)
	echo Launching $PNAME |hcat
	eval $PNAME 2>&1 |hcat
fi

echo "init.sh done event..."|hcat
echo "done" > $KAFL_CTL/control

if test -s /fuzz/progs.lst; then
	PNAME=$(rand_select /fuzz/progs.lst)
	TARGET=/fuzz/syz.prog
	hget "$PNAME" $TARGET
	syz-execprog -executor=/fuzz/syz-executor -repeat=2 -procs=1 -cover=0 $TARGET 2>&1 |hcat
	#syz-execprog -executor=/bin/true -repeat=2 -procs=1 -cover=0 $TARGET
fi

echo 0 > $TRACE_CTL/tracing_on
#cat $TRACE_CTL/trace |hcat
echo "pause" > $KAFL_CTL/control
echo "abort" > $KAFL_CTL/control

if grep -q tdx_fuzz $TRACE_CTL/trace; then
	echo "Payload in: $PNAME"|hcat
	#trace_push "$PNAME" |hcat
	#gcov_push "$PNAME"  |hcat
	all_push "$PNAME" |hcat
else
	echo "Payload out: $PNAME"|hcat
	test -n "$FILTER_EVENT" && echo $FILTER_EVENT > $KAFL_CTL/control
fi

echo "done" > $KAFL_CTL/control

fatal "init.sh: reached end of script"
