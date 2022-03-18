# Copyright (C) Intel Corporation, 2022
# SPDX-License-Identifier: MIT

.PHONY: env update install

env: .env .west
ifeq ($(PIPENV_ACTIVE), 1)
	@echo "Already inside pipenv. Skipping."
else
	pipenv shell
endif

.env: .west .pipenv manifest/create_env.sh
	@# do not write .env on script failure
	pipenv run bash ./manifest/create_env.sh > .env.out
	mv .env.out .env

.west: | .pipenv
	pipenv run west init -l manifest
	@# minimum install for manifest import!
	pipenv run west update kafl

.pipenv:
	sudo apt install python3-pip
	pip install -U pipenv
	pipenv install west
	@touch .pipenv

install:
ifneq ($(PIPENV_ACTIVE), 1)
	@echo "Error: Need to run inside pipenv. Abort."
else
	./kafl/install.sh check
	./kafl/install.sh deps
	./kafl/install.sh perms
	./kafl/install.sh qemu
	./kafl/install.sh radamsa
	make -C $(KAFL_ROOT) install
endif

update:
ifneq ($(PIPENV_ACTIVE), 1)
	@echo "Error: Need to run inside pipenv. Abort."
else
	west update -k
	pipenv run bash ./manifest/create_env.sh > .env
endif
