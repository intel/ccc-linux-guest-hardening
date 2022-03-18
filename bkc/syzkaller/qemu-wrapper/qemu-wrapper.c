/**
 * 
 * Copyright (C)  2022  Intel Corporation. 
 * 
 * This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
 * This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
 *
 **/
// SPDX-License-Identifier: MIT

#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
#include <linux/limits.h>

//#define DEBUG

int find_arg_id(char *argv[], char *str, int exact) {
	int i = 0;
	char *arg = argv[i];
	const char *vm = NULL;

	while (arg != NULL) {
		if (exact) {
			if (!strcmp(arg, str))
				return i;
		} else {	
			arg = strstr(arg, str);
			if (arg != NULL)
				break;
		}
		arg = argv[++i];
	}
	if (arg == NULL)
		return -1;
	return i;
}

int main(int argc, char *args[]) {
	/*
	 * Syzkaller may try to check version of the qemu,
	 * so we handle that separately
	 */
	if (argc == 2 && strcmp(args[1], "--version") == 0) {
		char * envp[] = { NULL};
		char *argv[] = {"qemu-system-x86_64", "--version"};

		execve(QEMU, argv, envp);
		return 0;
	}
	char* envp[] = { "QEMU_BIOS_IN_RAM=1", NULL };
	char* argv[] = {
		"qemu_wrapper",
		"-chardev", "socket,id=SOCKSYZ,server=on,nowait,host=localhost,port=51727",
		"-mon", "chardev=SOCKSYZ,mode=control",
		"-name", "VM-0",
		"-device", "virtio-rng-pci",
		"-display", "none",
		"-enable-kvm",
		"-machine", "q35,accel=kvm,kernel_irqchip,sata=false,smbus=false",
		"-smp", "3",
		"-bios", BIOS,
		"-m", "6G",
		"-cpu", "host,host-phys-bits,-la57",
		"-kernel", "KERNEL_PATH_GOES_HERE",
		"-nodefaults",
		"-drive", "id=drive0,file=DISK_PATH_GOES_HERE,if=virtio",
		"-snapshot",
		"-device", "virtio-serial",
		"-device", "virtconsole,chardev=stdio",
		"-chardev", "stdio,mux=on,id=stdio,signal=off",
		"-device", "isa-serial,chardev=stdio",
		"-netdev", "NETDEV_ARG_GOES_HERE",
		"-device", "virtio-net-pci,netdev=net0",
		"-append", "earlyprintk=ttyS0 console=hvc0 init=/sbin/init root=/dev/vda rw nokaslr tdx_wlist_devids=pci:0x8086:0x29c0,acpi:PNP0501 force_tdx_guest mitigations=off mce=off",
		"-no-reboot",
		"-nographic",

	       	NULL };
#ifdef DEBUG
	/* Log args passed to the wrapper */
	{
		FILE *f = fopen("wrapper.log" ,"a");

		if (f != NULL) {
			const char *p = args[0];
			int k = 0;
			while ( p != NULL) {
				fprintf(f, "%d: args[%d] = \"%s\"\n", getpid(), k, p);
				p = args[++k];
			}
		}
		fclose(f);
	}
#endif

	/* Fix VM name */
	int argv_vm_name_id = find_arg_id(argv, "VM-", 0);
	int args_vm_name_id = find_arg_id(args, "VM-", 0);

	if (argv_vm_name_id < 0 || args_vm_name_id < 0) {
		fprintf(stderr, "VM name arg not found\n");
		return EINVAL;
	}
	argv[argv_vm_name_id] = args[args_vm_name_id];
	/* Fix socket port */
	int argv_socket_id = find_arg_id(argv, "socket,id=SOCKSYZ", 0);
	int args_socket_id = find_arg_id(args, "socket,id=SOCKSYZ", 0);

	if (argv_socket_id < 0 || args_socket_id < 0) {
		fprintf(stderr, "Socket id arg not found\n");
		return EINVAL;
	}
	argv[argv_socket_id] = args[args_socket_id];

	/* Fix SSH host fwd port */
	int argv_netdev_id = find_arg_id(argv, "-netdev", 1);
	int args_netdev_id = find_arg_id(args, "-netdev", 1);

	if (argv_netdev_id < 0 || args_netdev_id < 0) {
		fprintf(stderr, "netdev arg not found\n");
		return EINVAL;
	}
	argv[argv_netdev_id + 1] = args[args_netdev_id + 1];

	/* Fix smp parameter */
	int argv_smp_id = find_arg_id(argv, "-smp", 1);
	int args_smp_id = find_arg_id(args, "-smp", 1);

	if (argv_smp_id < 0 || args_smp_id < 0) {
		fprintf(stderr, "-smp arg not found\n");
		return EINVAL;
	}
	argv[argv_smp_id + 1] = args[args_smp_id + 1];

	/* Fix mem parameter */
	int argv_mem_id = find_arg_id(argv, "-m", 1);
	int args_mem_id = find_arg_id(args, "-m", 1);

	if (argv_mem_id < 0 || args_mem_id < 0) {
		fprintf(stderr, "-m parameter not found\n");
		return EINVAL;
	}
	argv[argv_mem_id + 1] = args[args_mem_id + 1];

	/* Fix kernel path */
	int argv_kernel_id = find_arg_id(argv, "-kernel", 1);
	int args_kernel_id = find_arg_id(args, "-kernel", 1);

	if (argv_kernel_id < 0 || args_kernel_id < 0) {
		fprintf(stderr, "-kernel parameter not found\n");
		return EINVAL;
	}
	argv[argv_kernel_id + 1] = args[args_kernel_id + 1];

	/* Fix hda parameter to virtio */
	int argv_disk_id = find_arg_id(argv, "-drive", 1);
	int args_disk_id = find_arg_id(args, "-hda", 1);
	char drive_arg[PATH_MAX + 100];

	if (argv_disk_id < 0 || args_disk_id < 0) {
		fprintf(stderr, "-hda parameter is missing\n");
		return EINVAL;
	}
	snprintf(drive_arg, sizeof(drive_arg), "id=drive0,file=%s,if=virtio", args[args_disk_id + 1]);
	argv[argv_disk_id + 1] = drive_arg;

#ifdef DEBUG
	/* Log args generated by the wrapper */
	{
		FILE *f = fopen("wrapper.log" ,"a");

		if (f != NULL) {
			const char *p = argv[0];
			int k = 0;
			while (p != NULL) {
				fprintf(f, "%d: argv[%d] = \"%s\"\n", getpid(), k, p);
				p = argv[++k];
			}
		}
		fclose(f);
	}
#endif
#ifdef DEBUG
	/* Readable qemu cmdline */
	{
		char *p = argv[1];
		int k = 1;

		printf("%s ", QEMU);
		while (p != NULL) {
			printf("%s ", p);
			p = argv[++k];
		}
	}
#endif

	if (execve(QEMU, argv, envp) == -1) {
		fprintf(stderr, "execve QEMU failed\n");
		return 1;
	}
	return 0;
}
