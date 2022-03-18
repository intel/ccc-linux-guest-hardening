#!/bin/bash

# Copyright (C) Intel Corporation, 2022
# SPDX-License-Identifier: MIT
#
# Generate a .env file to be sourced by pipenv
# If you don't use west, customize .env for your own repo locations.

set -e

if ! which west > /dev/null; then
	echo "Could not find west. Run this script from within the west workspace and python venv."
	exit -1
fi

if ! west list manifest > /dev/null; then
	echo "Failed to locate West manifest - not initialized?"
	exit -1
fi

# silence missing Zephyr install?
if ! west list zephyr > /dev/null 2>&1; then
   if ! west config zephyr.base > /dev/null; then
	   west config zephyr.base not-using-zephyr
   fi
fi

BKC_ROOT=$(west topdir); echo BKC_ROOT=$BKC_ROOT
LINUX_GUEST=$(west list -f {abspath} linux-guest); echo LINUX_GUEST=$LINUX_GUEST
LINUX_HOST=$(west list -f {abspath} linux-host); echo LINUX_HOST=$LINUX_HOST
TDVF_ROOT=$(west list -f {abspath} tdvf); echo TDVF_ROOT=$TDVF_ROOT
SMATCH_ROOT=$(west list -f {abspath} smatch); echo SMATCH_ROOT=$SMATCH_ROOT

# kAFL baseline
KAFL_ROOT=$(west list -f {abspath} kafl); echo KAFL_ROOT=$KAFL_ROOT
QEMU_ROOT=$(west list -f {abspath} qemu); echo QEMU_ROOT=$QEMU_ROOT
LIBXDC_ROOT=$(west list -f {abspath} libxdc); echo LIBXDC_ROOT=$LIBXDC_ROOT
CAPSTONE_ROOT=$(west list -f {abspath} capstone); echo CAPSTONE_ROOT=$CAPSTONE_ROOT
RADAMSA_ROOT=$(west list -f {abspath} radamsa); echo RADAMSA_ROOT=$RADAMSA_ROOT
PACKER_ROOT=$(west list -f {abspath} nyx-packer); echo PACKER_ROOT=$PACKER_ROOT

# default kAFL workdir + config
echo KAFL_CONFIG_FILE=$BKC_ROOT/bkc/kafl/kafl_config.yaml
echo KAFL_WORKDIR=/dev/shm/${USER}_tdfl
