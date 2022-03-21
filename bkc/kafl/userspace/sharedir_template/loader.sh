#!/bin/sh

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

# Minimal loader.sh with maximum verbosity.
# We don't ever want to fix this stage but
# load/update everything via hget

export PATH=$PATH:/fuzz

echo Get init.sh | hcat
hget init.sh /fuzz/init.sh 2>&1 | hcat
chmod a+x /fuzz/init.sh 2>&1 | hcat

echo Launch /fuzz/init.sh | hcat
/fuzz/init.sh 2>&1 | tee /fuzz/init.log |hcat

echo "Error: init.sh has returned - captured log:"|hcat
hcat < /fuzz/init.log

habort
