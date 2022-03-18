#!/bin/bash

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

if [  -z "`cat /etc/lsb-release | grep Ubuntu`" ]
then
	echo "Unsupported Linux distribution";
	exit
fi

sudo apt install build-essential bc kmod cpio flex libncurses5-dev libelf-dev libssl-dev bison \
			libglib2.0-dev libgcrypt20-dev zlib1g-dev autoconf automake libtool \
			libpixman-1-dev libnfs-dev libiscsi-dev libaio-dev libbluetooth-dev \
			libbrlapi-dev libbz2-dev libcap-dev libcap-ng-dev libcurl4-gnutls-dev \
			libgtk-3-dev libfdt-dev libexplain-dev


