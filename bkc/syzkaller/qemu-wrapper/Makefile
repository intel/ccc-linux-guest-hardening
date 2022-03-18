BIOS=$(shell realpath  ../../sdv/TDVF-acpitest-072120.fd)
QEMU=$(shell realpath ../build/qemu-4.2.0/build/x86_64-softmmu/qemu-system-x86_64)

qemu-wrapper: qemu-wrapper.c
	-gcc $< -o $@ -DQEMU=\"${QEMU}\" -DBIOS=\"${BIOS}\"

clean:
	rm -f qemu-wrapper
