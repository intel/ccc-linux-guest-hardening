# Copyright (C) Intel Corporation, 2022
# SPDX-License-Identifier: MIT
#
# Makefile recipies for managing kAFL workspace

# declare all targets in this variable
ALL_TARGETS:=deploy clean env sharedir
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

sharedir: SHELL:=bash
sharedir:
	source env.sh && $$BKC_ROOT/bkc/kafl/userspace/gen_sharedir.sh $$BKC_ROOT/sharedir

initrd.cpio.gz: SHELL:=bash
initrd.cpio.gz:
	source env.sh && $$BKC_ROOT/bkc/kafl/userspace/gen_buildroot.sh initrd.cpio.gz
