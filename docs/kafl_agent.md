# kAFL Agent Implementation

The following provide an overview on the kAFL Agent used for fuzzing the Linux guest.

## Overview

The kAFL agent is a required component when fuzzing with kAFL. It can be seen as a generic driver
for communicating with the host and implementing the actual fuzzing harnesses.

The kAFL agent for confidential compute fuzzing has evolved to support multiple approaches to easily define a harness. It comprises the following components:

* Simple state-machine to start, stop, resume input injection as well as raising faults or errors throughout the kernel
* Injection hooks placed in TDX #VE and paravirtualization handlers (MMIO, PIO, MSR, CPUID) as well as virtio accessor functions (MMIO, DMA)
* Flexible harness configuration based on Kconfig (hardcoded), kprobe (cmdline) or debugfs (runtime)
* Flexible statistics and logging capabilities based on redirecting printk() to the host

## Component Detail

### Agent State Machine

```c
kafl_event()
```

### Injection Hooks for Intel TDX

```c
tdx_fuzz() => kafl_fuzz_buffer()
```

### Harness Configuration

* see existing harness definitions in (../bkc/kafl/run_experiments.py)

### Logging and Debug

```
cmdline hprintf=4, plus hardcoded early-boot level
```

```shell
kafl_fuzz.py
  --log-hprintf
  --log-crashes
```

```shell
$workdir/
  dump/fuzzer_stats_dump.lst
  dump/stackdump_NNNNN.txt
```

## Porting

Cherry-picks agent components on top of your target tree.
Expect some churn due to ongoing refactoring/renaming of upstream TDX patches.
