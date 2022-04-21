#!/bin/bash

#
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and
# your use of them is governed by the express license under which they were
# provided to you ("License"). Unless the License provides otherwise, you may
# not use, modify, copy, publish, distribute, disclose or transmit this software
# or the related documents without Intel's prior written permission.  This
# software and the related documents are provided as is, with no express or
# implied warranties, other than those that are expressly stated in the License.
#
#
# SPDX-License-Identifier: MIT

# Automate steps to build Smatch, analyze a kernel, filter and transfer audit results

# Baseline smatch analysis with annotation by previous code review (input)
SMATCH_ANNOTATED=$(BKC_ROOT)/bkc/audit/sample_output/5.15-rc1/smatch_warns_5.15_tdx_allyesconfig_filtered_results_analyzed

# Generated smatch reports. Smatch creates them local to target
SMATCH_WARNS=$(LINUX_GUEST)/smatch_warns.txt                 # raw generated smatch warnings (audit list)
SMATCH_FILTERED=$(LINUX_GUEST)/smatch_warns_filtered.txt     # audit list filtered by relevant subsystems
SMATCH_TRANSFERRED=$(LINUX_GUEST)/smatch_warns_annotated.txt # audit list annotated based on prior review

# Programs / helpers
SMATCH_BIN=$(SMATCH_ROOT)/smatch
SMATCH_RUNNER=$(SMATCH_ROOT)/smatch_scripts/test_kernel.sh
SMATCH_FILTER=$(BKC_ROOT)/bkc/audit/process_smatch_output.py
SMATCH_TRANSFER=$(BKC_ROOT)/bkc/audit/transfer_results.py

REPORTS: $(SMATCH_WARNS) $(SMATCH_FILTERED) $(SMATCH_TRANSFERRED)

all: $(REPORTS)

smatch: $(SMATCH_BIN)

$(SMATCH_BIN): $(SMATCH_ROOT)/
	@echo "[*] Attempting to build Smatch..."
	sudo apt install libsqlite3-dev
	git -C $(SMATCH_ROOT) am $(BKC_ROOT)/bkc/audit/0001-check_host_input-add-a-pattern.patch
	make -C $(SMATCH_ROOT) -j $(nproc)

$(SMATCH_WARNS): $(SMATCH_BIN) $(LINUX_GUEST)/.config
	@echo "[*] Analysing the kernel. This can take some time.."
	(cd $(LINUX_GUEST) && $(SMATCH_RUNNER) --wlog $@)

$(SMATCH_FILTERED): $(SMATCH_WARNS)
	$(SMATCH_FILTER) -f -o $@ $^

$(SMATCH_TRANSFERRED): $(SMATCH_ANNOTATED) $(SMATCH_FILTERED)
	@echo "[*] Attempting to transfer annotations based on $(SMATCH_ANNOTATED)..."
	$(SMATCH_TRANSFER) -f -o $@ $^
