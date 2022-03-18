#!/bin/bash
# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#

./qemu-system-x86_64 name VM-6 -m 8000 -smp 2 -chardev socket,id=SOCKSYZ,server=on,nowait,host=localhost,port=999 -netdev user,id=net0,restrict=on,hostfwd=tcp:127.0.0.1:10022-:22 -kernel /root/tdx/linux-guest/bzImage-syzkaller
