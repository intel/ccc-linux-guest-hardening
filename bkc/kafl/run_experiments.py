#!/usr/bin/env python3

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

import re
import os
import pwd
import sys
import subprocess
import time
import argparse
import tempfile
import glob
from timeit import default_timer as timer
from datetime import timedelta
from threading import Thread, Lock
import threading, queue
import multiprocessing
import yaml


FUZZ_SH_PATH = os.path.expandvars("$BKC_ROOT/bkc/kafl/fuzz.sh")
DEFAULT_TIMEOUT_HOURS=2
DEFAULT_COV_TIMEOUT_HOURS=2
REPEATS=1
SEEDS_DIR =  os.path.expanduser("~/seeds/harnesses/")
#KAFL_EXTRA_FLAGS="-t 8 --t-soft 3 -tc --trace --log-crashes --kickstart 16"
KAFL_EXTRA_FLAGS="--trace --log-crashes"
HARNESS_PREFIX="CONFIG_TDX_FUZZ_HARNESS_"
KCFLAGS = "-fno-ipa-sra -fno-ipa-cp-clone -fno-ipa-cp"


#HARNESSES = ["DOINITCALLS_LEVEL_3", "DOINITCALLS_LEVEL_4", "DOINITCALLS_LEVEL_5", "DOINITCALLS_LEVEL_6", "DOINITCALLS_LEVEL_7", "CONFIG_TDX_FUZZ_HARNESS_POST_TRAP", "CONFIG_TDX_FUZZ_HARNESS_EARLYBOOT", "CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_PCI", "CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_VIRTIO", "CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_ACPI", "CONFIG_TDX_FUZZ_HARNESS_FULL_BOOT", "CONFIG_TDX_FUZZ_HARNESS_REST_INIT", "CONFIG_TDX_FUZZ_HARNESS_VIRTIO_BLK_PROBE", "BPH_VIRTIO_CONSOLE_INIT", "BPH_EARLY_PCI_SERIAL", "CONFIG_TDX_FUZZ_HARNESS_START_KERNEL", "CONFIG_TDX_FUZZ_HARNESS_DO_BASIC", "CONFIG_TDX_FUZZ_HARNESS_ACPI_EARLY_INIT"]

HARNESSES = [
        "DOINITCALLS_LEVEL_3",
        "DOINITCALLS_LEVEL_4",
        "DOINITCALLS_LEVEL_5",
        "DOINITCALLS_LEVEL_6",
        "DOINITCALLS_LEVEL_7",
        "CONFIG_TDX_FUZZ_HARNESS_POST_TRAP",
        "CONFIG_TDX_FUZZ_HARNESS_EARLYBOOT",
        "CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_PCI",
        "CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_VIRTIO",
        "CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_ACPI",
        "CONFIG_TDX_FUZZ_HARNESS_FULL_BOOT",
        "CONFIG_TDX_FUZZ_HARNESS_REST_INIT",
        "CONFIG_TDX_FUZZ_HARNESS_VIRTIO_BLK_PROBE",
        "CONFIG_TDX_FUZZ_HARNESS_START_KERNEL",
        "CONFIG_TDX_FUZZ_HARNESS_DO_BASIC",
        "CONFIG_TDX_FUZZ_HARNESS_ACPI_EARLY_INIT"]

#HARNESSES = ["DOINITCALLS_LEVEL_4"]

BPH_HARNESSES = [
        "BPH_ACPI_INIT",
        "BPH_VP_MODERN_PROBE",
        "BPH_VIRTIO_CONSOLE_INIT",
        "BPH_P9_VIRTIO_PROBE",
        "BPH_PCI_SUBSYS_INIT",
        "BPH_HANDLE_CONTROL_MESSAGE",
        "BPH_VIRTIO_PCI_PROBE",
        "BPH_PCIBIOS_FIXUP_IRQS"]

HARNESSES = HARNESSES + BPH_HARNESSES

HARNESS_TIMEOUT_OVERRIDES = {
        "FULL_BOOT": 24,
        "DOINITCALLS_LEVEL_6": 24,
        "DOINITCALLS_LEVEL_4": 24,
        "DO_BASIC": 24,
        }

# Harnesses that run FULL_BOOT with extra kernel boot params
BOOT_PARAM_HARNESSES = {
        "BPH_ACPI_INIT": "fuzzing_func_harness=acpi_init",
        "BPH_VP_MODERN_PROBE": "fuzzing_func_harness=vp_modern_probe fuzzing_disallow=virtio_pci_find_capability",
        "BPH_VIRTIO_CONSOLE_INIT": "fuzzing_func_harness=init",
        "BPH_VIRTIO_PCI_PROBE": "fuzzing_func_harness=virtio_pci_probe",
        "BPH_P9_VIRTIO_PROBE": "fuzzing_func_harness=p9_virtio_probe",
        "BPH_PCI_SUBSYS_INIT": "fuzzing_func_harness=pci_subsys_init",
        # TODO: kprobes not avail, do manual harness
        # "BPH_EARLY_PCI_SERIAL": "fuzzing_func_harness=setup_early_printk earlyprintk=pciserial,force,00:18.1,115200",
        "BPH_PCIBIOS_FIXUP_IRQS": "fuzzing_func_harness=pcibios_fixup_irqs acpi=noirq",
        "BPH_HANDLE_CONTROL_MESSAGE": "fuzzing_func_harness=handle_control_message fuzzing_disallow=virtio_pci_find_capability,pci_read_config_dword",
        #"FULL_BOOT": "tsc_early_khz=2600",
        }

KAFL_PARAM_HARNESSES = {
        "FULL_BOOT": "-t 8 -ts 3"
        }

DISABLE_HARNESSES = []

command_log = []

"""
# SET these in .config.tmpl
default_config_options = {"CONFIG_TDX_FUZZ_KAFL_DETERMINISTIC": "y",
        "CONFIG_TDX_FUZZ_KAFL_DISABLE_CPUID_FUZZ": "y",
        "CONFIG_TDX_FUZZ_KAFL_SKIP_IOAPIC_READS": "n",
        "CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO": "n",
        "CONFIG_TDX_FUZZ_KAFL_SKIP_RNG_SEEDING": "y",
        "CONFIG_TDX_FUZZ_KAFL_SKIP_MSR": "n",
        "CONFIG_TDX_FUZZ_KAFL_SKIP_PARAVIRT_REWRITE": "n",
        }
"""

harness_config_options = {
        "CONFIG_TDX_FUZZ_HARNESS_EARLYBOOT": {"CONFIG_TDX_FUZZ_KAFL_SKIP_PARAVIRT_REWRITE": "n"},
        "CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS": {"CONFIG_TDX_FUZZ_KAFL_SKIP_IOAPIC_READS": "y", "CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO": "y"},
        "CONFIG_TDX_FUZZ_HARNESS_FULL_BOOT": {"CONFIG_TDX_FUZZ_KAFL_SKIP_PARAVIRT_REWRITE": "y"},
        "CONFIG_TDX_FUZZ_HARNESS_POST_TRAP": {"CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO": "y", "CONFIG_TDX_FUZZ_KAFL_SKIP_PARAVIRT_REWRITE": "y"},
        "DOINITCALLS_LEVEL_7": {"CONFIG_TDX_FUZZ_KAFL_VIRTIO": "y"},
        "DOINITCALLS_LEVEL_6": {"CONFIG_TDX_FUZZ_KAFL_VIRTIO": "y"},
        "CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_VIRTIO": {"CONFIG_TDX_FUZZ_KAFL_VIRTIO": "y"},
        "BPH_VIRTIO_CONSOLE_INIT": {"CONFIG_TDX_FUZZ_KAFL_VIRTIO": "y"},
        "CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_PCI": {"CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO": "y"},
        "CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_VIRTIO": {"CONFIG_TDX_FUZZ_KAFL_VIRTIO": "y"},
        "CONFIG_TDX_FUZZ_HARNESS_START_KERNEL": {"CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO": "y"},
        }

config_options_dependencies = {}


kernel_build_mutex = Lock()
q = queue.Queue()

"""
Strips the CONFIG_TDX_HARNESS_ part from the harness name
"""
def normalize_harness_name(s):
    return s[len(HARNESS_PREFIX):] if s.startswith(HARNESS_PREFIX) else s

def linux_conf_harness_name(s):
    return HARNESS_PREFIX + normalize_harness_name(s)

def name_to_harness(s):
    s = s.split("-")[0] # Remove -tmpXXX
    if s.startswith("BPH_"):
        return s
    elif s.startswith("DOINITCALLS_LEVEL_"):
        return s

    return HARNESS_PREFIX + s

def get_kafl_config_boot_params():
    conf_file = os.environ.get("KAFL_CONFIG_FILE")
    with open(conf_file) as conf_yaml_file:
        conf = yaml.load(conf_yaml_file, Loader=yaml.FullLoader)
        default_append = conf.get("qemu_append", "")
        return default_append



def get_work_parallelism():
    with open(FUZZ_SH_PATH, "r") as fh:
        d = fh.read()
        matches = re.finditer("KAFL_FULL_OPTS=.*-p\s*(\d+).*", d)
        for m in matches:
            return int(m.group(1))

def parse_linux_config(fname):
    return HARNESSES

    """
    harnesses = []
    with open(fname, "r") as fh:
        config_data = fh.read()
        harness_re = re.finditer("CONFIG_TDX_FUZZ_HARNESS_[^=\s]+", config_data)
        for m in harness_re:
            harness = m.group(0)
            if harness in DISABLE_HARNESSES:
                continue
            harnesses.append(harness)
    return harnesses
    """
def generate_setups(harnesses):
    setups = set()
    for harness in harnesses:
        req_conf = ((harness, "y"),)
        harness_options = harness_config_options.get(harness, None)
        if harness_options:
            req_conf = req_conf + tuple(harness_options.items())
        if harness.startswith("DOINITCALLS_LEVEL"):
            level = harness[len("DOINITCALLS_LEVEL_"):]
            req_conf = req_conf + (("CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS", "y"), ("CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_LEVEL", level),)
        if harness.startswith("BPH_"):
            req_conf = req_conf + (("CONFIG_TDX_FUZZ_HARNESS_NONE", "y"),)
        setups.add(req_conf)
    return setups


def build_kernel(setup, linux_source, global_storage_dir, debug=False):

    out_stdout = subprocess.DEVNULL
    out_stderr = subprocess.DEVNULL
    if debug:
        out_stdout = None
        out_stderr = None

    harness = normalize_harness_name(setup[0][0])
    storage_dir = tempfile.mkdtemp(dir=global_storage_dir, prefix=harness+"-")
    campaign_name = os.path.basename(storage_dir)
    print(f"Configuring kernel for campaign '{campaign_name}'")

    old_cwd = os.getcwd()
    # Enter Linux CWD
    os.chdir(linux_source)
    kernel_build_mutex.acquire()
    subprocess.run(f"cp .config.tmpl .config", shell=True, stdout=out_stdout, stderr=out_stderr)

    print(f"Generating config for {setup}")
    for conf,val in setup:
        if val is None:
            # Handle after all values have been set
            pass
        else:
            subprocess.run(f"./scripts/config --set-val {conf} {val}", shell=True, stdout=out_stdout, stderr=out_stderr)
    # Unsets need to happen after setting vals
    for conf,val in setup:
        if val is None:
            subprocess.run(f"./scripts/config -d {conf}", shell=True, stdout=out_stdout, stderr=out_stderr)

    print("Building kernel")
    kernel_build_path = os.path.join(storage_dir, "build")
    os.makedirs(kernel_build_path, exist_ok=True)

    subprocess.run(f"make -j $(nproc) KCFLAGS=\"{KCFLAGS}\"", shell=True, stdout=out_stdout, stderr=out_stderr)
    #subprocess.run(f"make -j $(nproc)", shell=True, stdout=out_stdout, stderr=out_stderr)
    time.sleep(1)
    # Copy over built kernel to own directory
    subprocess.run(f"cp vmlinux System.map arch/x86/boot/bzImage .config {kernel_build_path}", shell=True, stdout=out_stdout, stderr=out_stderr)
    kernel_build_mutex.release()
    print(f"Copied kernel for campaign '{campaign_name}' to {kernel_build_path}")
    # Reset CWD
    os.chdir(old_cwd)
    return campaign_name


def run_setup(campaign_name, setup, linux_source, global_storage_dir, debug=False, cpu_offset=0, processes=1, dry_run=False):

    out_stdout = subprocess.DEVNULL
    out_stderr = subprocess.DEVNULL
    if debug:
        out_stdout = None
        out_stderr = None

    harness = normalize_harness_name(setup[0][0])
    print(f"Preparing campaign '{campaign_name}'")
    #campaign_name = time.strftime("%Y%m%d-%H%M%S")
    storage_dir = os.path.join(global_storage_dir, campaign_name)

    username = pwd.getpwuid(os.getuid()).pw_name
    workdir_path = f"/dev/shm/{username}_tdfl-{campaign_name}"

    kernel_build_path = os.path.join(storage_dir, "build")

    old_cwd = os.getcwd()

    # Get default seeds for harness
    seeds_dir = None
    harness_seeds = os.path.join(SEEDS_DIR, harness)
    if os.path.exists(harness_seeds):
        seeds_dir = harness_seeds
    else:
        print(f"Could not find seed dir {harness_seeds}")
    seed_str = f"--seed-dir {seeds_dir}" if seeds_dir else ""

    print(f"Running campaign {workdir_path} with seeds '{seeds_dir}'")
    dry_run_flags = "--abort-exec=10000" if dry_run else ""
    timeout = HARNESS_TIMEOUT_OVERRIDES.get(harness, DEFAULT_TIMEOUT_HOURS)
    kafl_config_boot_params = get_kafl_config_boot_params()
    kernel_boot_params = kafl_config_boot_params + " " + BOOT_PARAM_HARNESSES.get(harness, "")
    if len(kernel_boot_params) > 0:
        kernel_boot_params = f"--append=\'{kernel_boot_params}\'"
    kafl_harness_extra_params = KAFL_PARAM_HARNESSES.get(harness, "")
    try:

        exc_cmd = f"KAFL_WORKDIR={workdir_path} {FUZZ_SH_PATH} full {kernel_build_path} --abort-time={timeout} -p={processes} --cpu-offset={cpu_offset} {seed_str} {KAFL_EXTRA_FLAGS} {kafl_harness_extra_params} {dry_run_flags} {kernel_boot_params}"
        command_log.append(exc_cmd)
        #with open(os.path.join(workdir_path, "cmd"), "w") as f:
        #    print(exc_cmd, file=f)
        subprocess.run(exc_cmd, shell=True, timeout=timeout * 3600 + 60, stdout=out_stdout, stderr=out_stderr)
    except subprocess.TimeoutExpired as e:
        print(e)



    # Wait for stuff to settle down... might not be necessary
    print(f"Done running campaign {workdir_path}")
    time.sleep(2)

    subprocess.run(f"{FUZZ_SH_PATH} ranges {workdir_path} > {workdir_path}/pt_ranges.txt", shell=True, stdout=out_stdout, stderr=out_stderr)
    subprocess.run(f"mv {workdir_path}/* {storage_dir}", shell=True, stdout=out_stdout, stderr=out_stderr)
    subprocess.run(f"rm -r {workdir_path}", shell=True, stdout=out_stdout, stderr=out_stderr)

    target_dir = os.path.join(storage_dir, "target")
    if not os.path.isdir(target_dir):
        print(f"Could not find ./target/ in '{storage_dir}'. Something most likely went wrong. Doing a manual copy.")
        os.makedirs(target_dir, exist_ok=True)

    ## HACK: overwrite ./target/ copied by fuzz.sh since vmlinux could have changed due to parallel campaign compilation
    #subprocess.run(f"cp {kernel_build_path}/* {target_dir}", shell=True, stdout=out_stdout, stderr=out_stderr)



def worker(i, processes, stop, dry_run):
    cpu_offset = i*processes
    print(f"Starting worker thread {i} with cpu-offset {cpu_offset} (processes={processes})")
    while True:
        try:
            work_args = q.get(timeout=1)
            run_setup(*work_args, cpu_offset=cpu_offset, processes=processes, dry_run=dry_run)
            q.task_done()
        except queue.Empty:
            if stop():
                break

def do_cov(args):
    out_stdout = subprocess.DEVNULL
    out_stderr = subprocess.DEVNULL
    if args.debug:
        out_stdout = None
        out_stderr = None

    for d in glob.glob(args.storage_dir + "/*/"):
        exp_name = os.path.basename(os.path.normpath(d))
        harness = normalize_harness_name(name_to_harness(exp_name))
        if harness in args.skip_harness:
            continue

        # Skip coverage gathering for campaigns that already have linecov.lst
        if (not args.rerun) and os.path.exists(os.path.join(d, "traces/linecov.lst")):
            continue

        ncpu = args.processes * args.jobs
        kafl_config_boot_params = get_kafl_config_boot_params()
        kernel_boot_params = kafl_config_boot_params + " " + BOOT_PARAM_HARNESSES.get(harness, "")
        if len(kernel_boot_params) > 0:
            kernel_boot_params = f"--append=\'{kernel_boot_params}\'"

        cmd_cov = f"{FUZZ_SH_PATH} cov {d} -p {ncpu} {kernel_boot_params}"
        cmd_smatch = f"USE_GHIDRA=1 {FUZZ_SH_PATH} smatch {d}"
        print(f"Gathering coverage for '{d}' with -p {ncpu}")
        subprocess.run(cmd_cov, shell=True, stdout=out_stdout, stderr=out_stderr)
        subprocess.run(cmd_smatch, shell=True, stdout=out_stdout, stderr=out_stderr)
        #print(cmd_cov)
        #print(cmd_smatch)
        print(f"DONE Gathering coverage for '{d}' with -p {ncpu}\n")




def do_run(args):
    linux_src = args.linux_src
    storage_dir = args.storage_dir

    if not args.allow_existing_dir and os.path.isdir(storage_dir):
        print(f"Storage path '{storage_dir}' already exists. Please choose a new dir.")
        sys.exit(1)
    os.makedirs(storage_dir, exist_ok=True)

    linux_config_path = os.path.join(linux_src, ".config")
    linux_config_tmpl_path = os.path.join(linux_src, ".config.tmpl")
    linux_config_bak_path = os.path.join(linux_src, ".config.fuzz.bak")
    print(f"Backing up .config to {linux_config_bak_path}")
    subprocess.run(f"cp {linux_config_path} {linux_config_bak_path}", shell=True)
    if os.path.isfile(linux_config_tmpl_path):
        print(f"Using Kernel config template '{linux_config_tmpl_path}'")
    else:
        print(f"Kernel .config template file '{linux_config_tmpl_path}' does not exists, using ' {linux_config_path}'")
        subprocess.run(f"cp {linux_config_path} {linux_config_tmpl_path}", shell=True)


    harnesses = parse_linux_config(linux_config_path)
    setups = generate_setups(harnesses)
    print("Campaign will run {} different setups".format(len(setups)))

    # Start up workers
    if not args.overcommit and args.processes * args.jobs > multiprocessing.cpu_count():
        print(f"Requesting more threads than cores available ({args.processes} * {args.jobs} > {multiprocessing.cpu_count()})!! If you really want this, specify --overcommit")
        sys.exit(1)


    start = timer()

    for setup in setups:
        #run_setup(setup, linux_src, storage_dir, debug=args.debug)
        for i in range(REPEATS):
            # TODO: no need to build separate kernels for repeats. Needs refactoring
            campaign_name = build_kernel(setup, linux_src, storage_dir, debug=True)
            q.put((campaign_name, setup, linux_src, storage_dir, args.debug))

    threads = []
    # Condition variable. No need for it to be atomic..
    stop_threads = False
    for i in range(args.jobs):
        t = threading.Thread(target=worker, args=(i, args.processes, lambda: stop_threads, args.dry_run))
        threads.append(t)
        t.start()


    subprocess.run(f"mv {linux_config_bak_path} {linux_config_path}", shell=True)

    # block until all campaigns are done
    q.join()
    end = timer()
    print("Campaign ran {} different setups in {}".format(len(setups), (timedelta(seconds=end-start))))
    stop_threads = True
    for t in threads:
        t.join()

    out_stdout = subprocess.DEVNULL
    out_stderr = subprocess.DEVNULL
    if args.debug:
        out_stdout = None
        out_stderr = None

    print("Command log:")
    for cmd in command_log:
        print(cmd)
    print("END command log")

    if args.coverage:
        for d in glob.glob(storage_dir + "/*"):
            ncpu = args.processes * args.jobs
            harness = name_to_harness(d)
            if harness in args.skip_harness:
                continue
            kernel_boot_params = BOOT_PARAM_HARNESSES.get(harness, "")
            if len(kernel_boot_params) > 0:
                kernel_boot_params = f"--append=\'{kernel_boot_params}\'"

            cmd_cov = f"{FUZZ_SH_PATH} cov {d} -p {ncpu} {kernel_boot_params}"
            cmd_smatch = f"USE_GHIDRA=1 {FUZZ_SH_PATH} smatch {d}"
            print(f"Gathering coverage for '{d}' with -p {ncpu}")
            try:
                subprocess.run(cmd_cov, shell=True, stdout=out_stdout, stderr=out_stderr, timeout=DEFAULT_COV_TIMEOUT_HOURS*3600)
                subprocess.run(cmd_smatch, shell=True, stdout=out_stdout, stderr=out_stderr, timeout=DEFAULT_COV_TIMEOUT_HOURS*3600)
            except subprocess.TimeoutExpired as e:
                print(f"TIMEOUT while getting coverage for '{d}'")
            print(f"DONE Gathering coverage for '{d}' with -p {ncpu}")

def parse_args():

    def parse_as_path(pathname):
        return os.path.abspath(
                os.path.expanduser(
                    os.path.expandvars(pathname)))

    def parse_as_file(filename):
        expanded = parse_as_path(filename)
        if not os.path.exists(expanded):
            raise argparse.ArgumentTypeError("Failed to find file argument %s (expanded: %s)" % (filename, expanded))
        return expanded

    def parse_as_dir(dirname):
        expanded = parse_as_path(dirname)
        if not os.path.exists(expanded):
            raise argparse.ArgumentTypeError("Failed to find file argument %s (expanded: %s)" % (dirname, expanded))
        return expanded


    main_parser = argparse.ArgumentParser(description='kAFL TDX fuzzing experiments runner.')
    subparsers = main_parser.add_subparsers(dest='action', metavar='<action>', required=True)
    cov_parser = subparsers.add_parser("cov", help="collect coverage")
    run_parser = subparsers.add_parser("run", help="run campaigns")

    cov_parser.add_argument('storage_dir', metavar='<storage_dir>', type=str,
            help='target dir containing the results of prior fuzzing run')
    cov_parser.add_argument('--rerun', action="store_true",
            help='Force rerun of coverage gathering')

    run_parser.add_argument('linux_src', metavar='<linux_src>', type=parse_as_dir,
            help='path to your linux kernel tree')
    run_parser.add_argument('storage_dir', metavar='<storage_dir>', type=parse_as_path,
            help='target dir to store the results. will be created / must not exist.')

    run_parser.add_argument('--allow-existing-dir', action="store_true",
            help='Allow storing results in existing dir')
    run_parser.add_argument('--dry-run', action="store_true",
            help='Perform dry run')
    run_parser.add_argument('-c', '--coverage', action="store_true",
            help='Gather coverage + smatch after running campaigns')
    run_parser.add_argument('--launcher', type=parse_as_file, default="$BKC_ROOT/bkc/kafl/fuzz.sh",
            help='fuzzer launch script (default: $BKC_ROOT/bkc/kafl/fuzz.sh)')

    main_parser.add_argument('--debug', action='store_true',
            help='Turn on debug output (show fuzzer stdout/stderr)')
    main_parser.add_argument('-j', '--jobs', metavar='<n>', type=int, default=1,
            help='Parallel run/cov jobs (default: 1)')
    main_parser.add_argument('-p', '--processes', metavar='<n>', type=int, default=get_work_parallelism(),
            help='Parallel fuzzer instances (default: obtained from fuzz.sh)')
    main_parser.add_argument('--overcommit', type=bool, default=False,
            help='Overcommit parallelization')
    main_parser.add_argument('--skip-harness', nargs="*", type=str, default=[],
            help='Skip processing for specified harnesses')

    return main_parser.parse_args()

def main():

    args = parse_args()

    if not os.path.exists(FUZZ_SH_PATH):
        print("Could not find kAFL launcher in %s. Exit" % FUZZ_SH_PATH)
        return

    if not "KAFL_CONFIG_FILE" in os.environ:
        print("KAFL_CONFIG_FILE not in environment. Have you setup the right kAFL environment (make env)?")
        sys.exit(1)

    if args.action == "cov":
        do_cov(args)
    if args.action == "run":
        do_run(args)


if __name__ == "__main__":
    main()
