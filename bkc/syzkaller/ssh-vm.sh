#!/bin/bash

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

if [ -z "$VM_SSH_PORT" ]; then
	VM_SSH_PORT=10322
fi
if [ -z "$VM_SSH_KEY" ]; then
	VM_SSH_KEY=build/image/stretch.id_rsa
fi

ssh  -p $VM_SSH_PORT -i $VM_SSH_KEY root@localhost
