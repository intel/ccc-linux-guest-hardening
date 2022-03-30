# SPDX-License-Identifier: MIT
# Syzkaller compilation based on:
# https://github.com/google/syzkaller/blob/master/docs/linux/setup.md

.EXPORT_ALL_VARIABLES:
GOPATH=${PWD}/gopath
GOROOT=${PWD}/goroot
PATH:=${GOPATH}/bin:${GOROOT}/bin:${PATH}

GUEST:=guest-kernel
GUEST_BRANCH:=kafl/fuzz-5.15-3

default: syzkaller qemu guest-kernel guest-image

clean: clean_syzkaller clean_qemu clean_guest-kernel clean_guest-image

syzkaller: clean_syzkaller
	echo PATH=${PATH}
	echo GOPATH=${GOPATH}
	echo GOROOT=${GOROOT}
	wget https://dl.google.com/go/go1.18.linux-amd64.tar.gz
	tar -xf go1.14.2.linux-amd64.tar.gz
	rm -f go1.14.2.linux-amd64.tar.gz
	mv go goroot
	mkdir gopath
	go get -u -d github.com/google/syzkaller/prog
	make -C gopath/src/github.com/google/syzkaller/
	echo "SYZKALLER COMPILED!"

clean_syzkaller:
	rm -rf gopath
	rm -rf goroot
	rm -f *.tar.gz*

qemu: clean_qemu
	wget https://download.qemu.org/qemu-4.2.0.tar.xz
	tar xvf qemu-4.2.0.tar.xz
	cd qemu-4.2.0 && patch -p1 < ../qemu-bios.patch
	mkdir qemu-4.2.0/build && cd qemu-4.2.0/build && ../configure --enable-virtfs --target-list=x86_64-softmmu &&  make -j`nproc`
	echo "QEMU COMPILED!"

clean_qemu:
	rm -f qemu-4.2.0.tar.xz
	rm -rf qemu-4.2.0

guest-kernel:
	git clone --branch ${GUEST_BRANCH} {$LINUX_GUEST} ${GUEST}
	cp ../guest.config ${GUEST}/.config
	cd ${GUEST} && ./scripts/config -e CONFIG_KCOV
	cd ${GUEST} && ./scripts/config -e CONFIG_KCOV_INSTRUMENT_ALL
	cd ${GUEST} && ./scripts/config -e CONFIG_KCOV_ENABLE_COMPARISONS
	cd ${GUEST} && ./scripts/config -e CONFIG_DEBUG_FS
	cd ${GUEST} && ./scripts/config -e CONFIG_DEBUG_INFO
	cd ${GUEST} && ./scripts/config -e CONFIG_KALLSYMS
	cd ${GUEST} && ./scripts/config -e CONFIG_KALLSYMS_ALL
	cd ${GUEST} && ./scripts/config -e CONFIG_CONFIGFS_FS
	cd ${GUEST} && ./scripts/config -e CONFIG_SECURITYFS
	cd ${GUEST} && ./scripts/config -d CONFIG_RANDOMIZE_BASE
	cd ${GUEST} && ./scripts/config -d CONFIG_DEBUG_KMEMLEAK
	cd ${GUEST} && ./scripts/config -e CONFIG_FAULT_INJECTION
	cd ${GUEST} && ./scripts/config -e CONFIG_FAULT_INJECTION_DEBUG_FS
	cd ${GUEST} && ./scripts/config -e CONFIG_FAULT_INJECTION_USERCOPY
	cd ${GUEST} && ./scripts/config -e CONFIG_FAILSLAB
	cd ${GUEST} && ./scripts/config -e CONFIG_FAIL_PAGE_ALLOC
	cd ${GUEST} && ./scripts/config -e CONFIG_FAIL_MAKE_REQUEST
	cd ${GUEST} && ./scripts/config -e CONFIG_FAIL_IO_TIMEOUT
	cd ${GUEST} && ./scripts/config -e CONFIG_FAIL_FUTEX
	cd ${GUEST} && ./scripts/config -e CONFIG_GCOV_KERNEL
	cd ${GUEST} && ./scripts/config -e CONFIG_GCOV_FORMAT_AUTODETECT
	cd ${GUEST} && ./scripts/config -e CONFIG_GCOV_PROFILE_ALL
	cd ${GUEST} && yes "" | make oldconfig
	cd ${GUEST} && make bzImage -j`nproc`

clean_guest-kernel:
	rm -rf ${GUEST}

guest-image:
	cd image && rm ./create-image.sh
	cd image && wget https://raw.githubusercontent.com/google/syzkaller/master/tools/create-image.sh
	cd image && ./create-image.sh -s 10000
	cd image && rm ./create-image.sh

clean_guest-image:
	rm -rf image/chroot
	rm -f image/stretch.*
