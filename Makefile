# Copyright (C) Intel Corporation, 2022
# SPDX-License-Identifier: MIT
#
# Makefile recipies for managing kAFL workspace

# declare all targets in this variable
ALL_TARGETS:=deploy clean env prepare
# declare all target as PHONY
.PHONY: $(ALL_TARGETS)

# This small chunk of code allows us to pass arbitrary arguments to our make targets
# see the solution on SO:
# https://stackoverflow.com/a/14061796/3017219
# If the first argument is contained in ALL_TARGETS
ifneq ($(filter $(firstword $(MAKECMDGOALS)), $(ALL_TARGETS)),)
  # use the rest as arguments to create a new variable ADD_ARGS
  EXTRA_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  # ...and turn them into do-nothing targets
  $(eval $(EXTRA_ARGS):;@:)
endif

all: deploy

deploy:
	make -C deploy $@ -- $(EXTRA_ARGS)

clean:
	make -C deploy $@

env: SHELL:=bash
env: env.sh
	@echo "Entering environment in sub-shell. Exit with 'Ctrl-d'."
	@PROMPT_COMMAND='source env.sh; unset PROMPT_COMMAND' $(SHELL)

auditconf := bkc/kafl/linux_kernel_tdx_guest.config
auditlogs := smatch_warns_annotated.txt
assets := sharedir initrd.cpio.gz disk.img

sharedir:
	+BASH_ENV=env.sh bash bkc/kafl/userspace/gen_sharedir.sh $@

initrd_buildroot.cpio.gz:
	+BASH_ENV=env.sh bash bkc/kafl/userspace/gen_buildroot.sh $@

initrd_busybox.cpio.gz:
	+BASH_ENV=env.sh bash bkc/kafl/userspace/gen_initrd.sh $@

initrd.cpio.gz: initrd_busybox.cpio.gz
	+BASH_ENV=env.sh ln -sf $^ $@

disk.img:
	qemu-img create -f qcow2 $@ 1024M

$(auditlogs): $(auditconf)
	+BASH_ENV=env.sh bash bkc/audit/smatch_audit.sh . $^

prepare: $(assets) $(auditlogs)
