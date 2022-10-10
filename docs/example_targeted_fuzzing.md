# Selective kprobe-based harnessing: an example

This example demonstrates how to customize fuzzing for specific target functions via [kprobe-based harnessing](../bkc/kafl#selective-kprobe-based-harnessing-for-linux). Targeted fuzzing can be useful when a bug report lacks a working corpus for reproducing crashes. In addition, it can optimize fuzzing resource allocation for specific subsystems or execution paths.

## The Walk-Through
All subsequent steps assume a successful installation and an activated environment.

### 0. Preparing the Target Function 
In order to observe deterministic behaviors, this example uses a synthetic function `call_bugs_uaf()` as the target function to inject Use-After-Free (UAF) type of vulnerabilities in `$LINUX_GUEST/init/main.c`:
```c
noinline void call_bugs_uaf(void){
	int * buf;
        unsigned long long msr_val;

	buf = kmalloc(sizeof(int), GFP_KERNEL);
	msr_val = native_read_msr(0x42);
	kfree(buf);
        if (msr_val == 0x41) {
		*buf = 7; // UAF
        }
        if (msr_val == 0x42) {
		kfree(buf); // double free
        }
}
```

The target function is placed at a later stage after the kernel is initialized.
```c
static void __init do_basic_setup(void)
{
        ... ...
	do_initcalls();
        
        call_bugs_uaf();
}
```

Note this preparation can be skipped when using existing functions as targets.

### 1. Configuring Linux Guest Kernel:

Before building the Linux guest kernel, ensure the following configurations in the `$LINUX_GUEST/.config` for kprobe-based harnessing:
```
CONFIG_TDX_FUZZ_HARNESS_NONE=y
CONFIG_KPROBES=y
CONFIG_HAVE_KPROBES=y
```

### 2. Launching the Fuzzer

The example uses `--append="fuzzing_func_harness=<function_name>` to specify the function for fuzzing and enables crash report via `--log-crashes`:


```shell
./fuzz.sh run $LINUX_GUEST/ -p 1 --append="fuzzing_func_harness=call_bugs_uaf" --log-crashes

... ...
[QEMU-Nyx] Booting VM to start fuzzing...
Worker-00 entering fuzz loop..
00:00:10: Got    1 from    0: exit=R, 232/ 0 bits, 232 favs, 1.88msec, 0.2KB (kickstart)
00:00:15: Got    2 from    1: exit=R,  4/ 0 bits,  8 favs, 0.28msec, 0.0KB (trim)
00:00:15: Got    3 from    1: exit=K, 1412/ 0 bits,  0 favs, 7.86msec, 0.0KB (redq_mutate)
00:00:15: Got    4 from    1: exit=K,  6/48 bits,  0 favs, 4.80msec, 0.0KB (redq_mutate)
00:00:34:  1685 exec/s,  236 edges, 50% favs pending, findings: <0, 2, 0>
```

After manually terminating the fuzzing, show an example crash report as follows:
```
Received Ctrl-C, killing workers...
... ...

cat $KAFL_WORKDIR/logs/kasan_58af34.log
==================================================================
BUG: KASAN: use-after-free in call_bugs_uaf+0x170/0x190
Write of size 4 at addr ffff8880346cfbf0 by task swapper/1

CPU: 0 PID: 1 Comm: swapper Not tainted 5.15.0-rc6-g5c88c2b4792f-dirty #66
Call Trace:
 dump_stack_lvl+0x28/0x33
 print_address_description.constprop.0+0x34/0x2c0
 ? call_bugs_uaf+0x170/0x190
 kasan_report.cold+0xd7/0x1fe
 ? call_bugs_uaf+0x170/0x190
 __asan_report_store4_noabort+0x27/0x40
 call_bugs_uaf+0x170/0x190
 elfcorehdr_read+0x60/0x60
 kernel_init_freeable+0x1ff/0x264
 ? rest_init+0x1c0/0x1c0
 kernel_init+0x29/0x210
 ret_from_fork+0x1f/0x30
 
... ...

The buggy address belongs to the object at ffff8880346cfbf0
 which belongs to the cache kmalloc-8 of size 8
The buggy address is located 0 bytes inside of
 8-byte region [ffff8880346cfbf0, ffff8880346cfbf8)
The buggy address belongs to the page:
page:ffffea0000d1b380 refcount:1 mapcount:0 mapping:0000000000000000 index:0xffff8880346cfd68 pfn:0x346ce
head:ffffea0000d1b380 order:1 compound_mapcount:0
flags: 0x4000000000010200(slab|head|zone=1)
raw: 4000000000010200 ffff888007840448 ffff888007840448 ffff888007842540
raw: ffff8880346cfd68 0000000000150014 00000001ffffffff 0000000000000000
page dumped because: kasan: bad access detected

Memory state around the buggy address:
 ffff8880346cfa80: fc fc fc fc fc fc fc fc fc fc fc fc fc fc fc fc
 ffff8880346cfb00: fc fc fc fc fc fc fc fc fc fc fc fc fc fc fc fc
>ffff8880346cfb80: fc fc fc fc fc fc fc fc fc fc fc fc fc fc fa fc
                                                             ^
... ...
```

### 3. Reproducing and Debugging
To reproduce the crash and debug:
```
./fuzz.sh debug $KAFL_WORKDIR $KAFL_WORKDIR/corpus/kasan/payload_00001
```

Use another session for debugging:
```shell
gdb $LINUX_GUEST/vmlinux

# In GDB session
(gdb) target remote localhost:1234
Remote debugging using localhost:1234
0xffffffff810fc351 in kAFL_hypercall (p2=0, p1=12) at ./arch/x86/include/asm/kafl-api.h:108
108             asm volatile ("vmcall"
(gdb) hb call_bugs_uaf
Hardware assisted breakpoint 1 at 0xffffffff810020e0: file init/main.c, line 747.
... ...
```

## Notes:
### 1. It is advisable to ensure the compiler avoids inlining the fuzzing target function when it is simple and small. Otherwise, kprobe based harness may stop working, and all fuzzing instances will be stuck at "waiting." This is because of a known kprobe [limitation](https://docs.kernel.org/trace/kprobes.html):
- > If you install a probe in an inline-able function, Kprobes makes no attempt to chase down all inline instances of the function and install probes there.  gcc may inline a function without being asked, so keep this in mind if you're not seeing the probe hits you expect.

### 2. The fuzzing instance can also be stuck at "waiting" if no sufficient input can be fuzzed in the target function.

### 3. An early crash may happen 'outside' the fuzzing trap, causing fuzzing abort as qemu crash and resulting in crash not collected and no corpus. This might be investigated for a fix later.