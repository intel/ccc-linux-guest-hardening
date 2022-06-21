#!/bin/bash

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

mount -t debugfs none /sys/kernel/debug/
KAFL_CTL=/sys/kernel/debug/kafl

echo "[*] kAFL userspace harness RESUME_SUSPEND. Agent status:"
grep . $KAFL_CTL/*
grep . $KAFL_CTL/status/*

## BEGIN HARNESS

echo "ls /sys/power"
ls /sys/power
echo 1 > /sys/module/suspend/parameters/pm_test_delay
echo N > /sys/module/printk/parameters/console_suspend
#echo devices > /sys/power/pm_test
#echo processors > /sys/power/pm_test
echo core > /sys/power/pm_test
echo platform > /sys/power/disk
#echo test_resume > /sys/power/disk
echo "start"  > $KAFL_CTL/control
echo disk > /sys/power/state
echo "done"  > $KAFL_CTL/control

## END HARNESS
