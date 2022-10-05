# Selective kprobe-based harnessing: an example

This example demonstrates how to customize fuzzing for specific target functions via [kprobe-based harnessing](../bkc/kafl#selective-kprobe-based-harnessing-for-linux). Targeted fuzzing can be useful when a bug report lacks a working corpus for reproducing crashes. In addition, it can optimize fuzzing resource allocation for specific subsystems or execution paths.

## The Walk-Through
All subsequent steps assume a successful installation and an activated environment.

### 0. Preparing the Target Function 
In order to observe deterministic behaviors, this example uses a synthetic function `call_bug_uaf()` as the target function to inject an Use-After-Free (UAF) vulnerability in `$LINUX_GUEST/init/main.c`:
```c
noinlne void call_bug_uaf(void){
	int * buf;
	buf = kmalloc(sizeof(int), GFP_KERNEL);
	*buf = native_read_msr(0x42);
	kfree(buf);
	*buf = 7;
}
```

The target function is placed at a later stage after the kernel is initialized.
```c
static void __init do_basic_setup(void)
{
        ... ...
	do_initcalls();
        
        call_bug_uaf();
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
./fuzz.sh run $LINUX_GUEST/ -p 1 --append="fuzzing_func_harness=call_bug_uaf" --log-crashes

... ...
[QEMU-Nyx] Booting VM to start fuzzing...
Worker-00 entering fuzz loop..
00:00:10: Got    1 from    0: exit=K, 1381/ 0 bits,  0 favs, 18.77msec, 0.2KB (kickstart)
00:00:10: Got    2 from    0: exit=K,  1/ 0 bits,  0 favs, 5.98msec, 0.2KB (kickstart)
00:00:18: Got    3 from    2: exit=K, 43/ 2 bits,  0 favs, 5.38msec, 0.2KB (redq_mutate)
Worker-00 Redqueen: Input 3 not stable, skipping..
00:00:22: Got    4 from    1: exit=R,  8/ 0 bits,  8 favs, 0.30msec, 0.0KB (afl_havoc)
00:00:22: Got    5 from    1: exit=K,  7/ 0 bits,  0 favs, 8.13msec, 0.0KB (afl_havoc)
00:00:28: Got    6 from    2: exit=K,  8/23 bits,  0 favs, 4.50msec, 0.0KB (afl_havoc)
 0:00:45:   202 exec/s,    8 edges,  0% favs pending, findings: <0, 5, 0>

```

After manually terminating the fuzzing, show an example crash report as follows:
```
Received Ctrl-C, killing workers...
... ...

cat $KAFL_WORKDIR/logs/kasan_0e2f85.log 
==================================================================
BUG: KASAN: use-after-free in call_bug_uaf+0x147/0x180
Write of size 4 at addr ffff88800876dbf0 by task swapper/1

CPU: 0 PID: 1 Comm: swapper Not tainted 5.15.0-rc6-g5c88c2b4792f-dirty #64
Call Trace:
 dump_stack_lvl+0x28/0x33
 print_address_description.constprop.0+0x34/0x2c0
 ? call_bug_uaf+0x147/0x180
 kasan_report.cold+0xd7/0x1fe
 ? call_bug_uaf+0x147/0x180
 __asan_report_store4_noabort+0x27/0x40
 call_bug_uaf+0x147/0x180
 elfcorehdr_read+0x60/0x60
 kernel_init_freeable+0x1ff/0x264
 ? rest_init+0x1c0/0x1c0
 kernel_init+0x29/0x210
 ret_from_fork+0x1f/0x30
 ... ...
```

### 3. Reproducing and Debugging
To reproduce the crash and debug:
```
./fuzz.sh debug $KAFL_WORKDIR $KAFL_WORKDIR/corpus/kasan/payload_00001
```

Use another session for debugging:
```
gdb $LINUX_GUEST/vmlinux

# In GDB session
(gdb) target remote localhost:1234
Remote debugging using localhost:1234
0xffffffff810fc341 in kAFL_hypercall (p2=0, p1=12) at ./arch/x86/include/asm/kafl-api.h:108
108             asm volatile ("vmcall"
(gdb) hb call_bug_uaf
Hardware assisted breakpoint 1 at 0xffffffff810020e0: file init/main.c, line 738.
... ...
```

## Notes:
### 1. It is advisable to ensure the compiler avoids inlining the fuzzing target function when it is simple and small. Otherwise, kprobe based harness may stop working, and all fuzzing instances will be stuck at "waiting." This is because of a known kprobe [limitation](https://docs.kernel.org/trace/kprobes.html):
- > If you install a probe in an inline-able function, Kprobes makes no attempt to chase down all inline instances of the function and install probes there.  gcc may inline a function without being asked, so keep this in mind if you're not seeing the probe hits you expect.

### 2. The fuzzing instance can also be stuck at "waiting" if no sufficient input can be fuzzed in the target function.

### 3. An early crash may happen 'outside' the fuzzing trap, causing fuzzing abort as qemu crash and resulting in crash not collected and no corpus. This might be investigated for a fix later.





