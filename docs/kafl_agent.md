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

The kAFL agent exposes a function `kafl_fuzz_event()` inside the kernel for programmatic configuration of start and endpoints of a fuzzing iteration, pause input injection or raise faults such as #GP or KASAN errors. The following options are understood:

* KAFL_ENABLE - enable input injection (but wait for first input request to actually trigger KAFL_START logic)
* KAFL_START - connect to kAFL fuzzer, check configuration, setup payload buffer, trigger root VM snapshot (start of fuzzing loop)
* KAFL_DONE - mark end of fuzzing loop, return execution result "OK" to fuzzer (and eventually restore the snapshot)
* KAFL_PANIC, KAFL_KASAN, KAFL_UBSAN - return execution result "PANIC" or "KASAN" to fuzzer (and restore the snapshot)
* KAFL_ERROR, KAFL_HALT, KAFL_REBOOT, KAFL_SAFE_HALT - catch "safe" failure conditions by returning OK (and restore snapshot)
* KAFL_ABORT - raise fatal error in harness setup or usage, e.g. fuzzer payload too large for guest buffer (fuzzer exit)

Additional/special options:
* KAFL_TRACE - dump current injection stats via printk (normally reset on START and printed on DONE)
* KAFL_PAUSE, KAFL_RESUME - set/unset a flag to temporarility disable input injection by `kafl_fuzz_buffer()`
* KAFL_SETCR3 - set the CR3 filter for the Intel PT coverage tracing to current guest value (set once before KAFL_START)

The interface is extensively used for fuzzing different phases of Linux boot in `init/main.c`.

### Injection Hooks for Intel TDX

Given the above fuzzer interface, a simple harness around PCI initialization phase might look like this:

```c
kafl_fuzz_event(KAFL_ENABLE);
pci_init();
[...]
kafl_fuzz_event(KAFL_DONE); // somewhere later in the kernel
```

Note that there is no fuzzing input provided to the target function. Instead of fuzzing arguments to `pci_init()`, our goal is to inject fuzzing inputs to any untrusted VMM input that pci_init() migt request via various HW accessor functions, paravirtualization, shared memory etc.

The Linux kernel subsystem for TDX offers two function hooks for injecting input on untrusted VMM-to-guest interfaces:
* `tdx_fuzz()` allows to replace the value of VMM return values (MMIO, PIO, MSR, CPUID)
* `tdx_fuzz_err()` allows to fuzz the corresponding error code of the input requests

In addition, our kAFL agent patches also hook virtio accessor functions for MMIO and shared memory/DMA:
* `__cpu_to_virtioNN()` in `include/linux/virtio_byteorder.h`
* `virtqueue_get_buf()` in `drivers/virtio/virtio_ring.c`

In each case, the function `kafl_fuzz_buffer()` is called. The function
* checks if injection is enabled (ENABLE/PAUSE/RESUME)
* checks if the input type/address should be fuzzed (see harness configuration)
* initializes the fuzzer loop if not already done (ENABLE=>START)
* records statistics and debug info (see logging/debug section)
* returns the requested number of bytes from the fuzzing input buffer

That function iteratively consumes the fuzzer input. If the provided fuzzer input is too short for the current execution the injection is aborted and the fuzzing loop prematurely returns with OK state. This forces the fuzzer to expand the payload as needed to properly explore the target.

### Harness Configuration

The scope of a fuzzing execution (start/end) can be defined in multiple ways:
* Hardcoded. See various boot phase harnesses in `init/main.c` and exposed as CONFIG_TDX_FUZZ_HARNESS_* in Kconfig
* Kprobe. Configured pre/post execution hooks on kernel cmdline to start/stop/pause a injection around specific functions. See BPH_* harnesses.
* Usermode. Configured via debugfs interface to start/stop injection around special usermode stimulus, such as `lspci` or `dhcp`. See US_* harnesses.

The input injection of a harness is separately defined via `kafl_fuzz_filter()` in `kafl-agent.c`. The most common types of input injection are exposed as Kconfig options:
* CONFIG_TDX_FUZZ_KAFL_VIRTIO - enable injection of type VIRTIO (mmio/shm) 
* CONFIG_TDX_FUZZ_KAFL_SKIP_MSR - disable injection of MSRs via tdx_fuzz()
* CONFIG_TDX_FUZZ_KAFL_SKIP_CPUID - disable injection of CPUIDs 
* CONFIG_TDX_FUZZ_KAFL_SKIP_IOAPIC_READS - disable injection of specific MMIO ranges
* CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO - disable injection of specific PIO ranges

The filters are defined based on previously experienced fuzzing roadblocks. For instance, CPUID injection was too broad leading to false positives, and ACPI/IOAPIC injection tends to cause significant slowdown and crashes in ACPI subsystems.

Additional useful options exposed via Kconfig:
* CONFIG_TDX_FUZZ_KAFL_DEBUGFS - enable DEBUGFS interface for fuzzing from userspace
* CONFIG_TDX_FUZZ_KAFL_TRACE_LOCATIONS - enable KAFL_TRACE event and print location stats after each execution
* CONFIG_TDX_FUZZ_KAFL_DETERMINISTIC - patch kernel workqueue and bypass RNG seeding to make execution more deterministic
* CONFIG_TDX_FUZZ_KAFL_SKIP_RNG_SEEDING - initialize RNG from fixed value, not fuzzing input
* CONFIG_TDX_FUZZ_KAFL_SKIP_PARAVIRT_REWRITE - skip runtime rewrite of paravirt handlers (can cause PT decode errors)

Best known defaults are encoded in existing harness definitions in `bkc/kafl/run_experiments.py`. Expected results and known issues shall be documented in `docs/boot_harnesses.md`.

### Logging and Debug

Kernel printk facility is redirected to log messages via hypercalls (`kafl_hprintf()`). The loglevel can be set using `hprintf=` cmdline on kernel boot. For debugging, enable storing per-VM logs using `kafl fuzz --log-hprintf` option. This can overflow a disk quickly, so normal fuzzing operation should be done with `--log-crashes`.

The kAFL agent also supports printing 3 types of debug/trace statistics. This is done only once for every new input found by the fuzzer, and enabled using a special `agent_flags` field in the payload buffer:
* dump_stats - write a line of input injection stats at end of execution
* dump_callers - dump the call stack before every performed input injection
* dump_observed - record complete observed input stream provided to kernel (injected or original input, depending on injection settings and input length)

When set, the information is collected and uploaded to the host (see `kafl-agent.c`), where it accumulates in the fuzzer workdir:

```shell
$workdir/
  dump/fuzzer_location_stats.lst
  dump/stackdump_NNNNN.log
  dump/payload_NNNNN
```


## Porting

Cherry-picks agent components on top of your target tree.
Expect some churn due to ongoing refactoring/renaming of upstream TDX patches.
