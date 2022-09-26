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
import sys
import shutil
import subprocess as p
import argparse
import yaml

from pprint import pprint, pformat

boot_harnesses = [
        "BOOT_POST_TRAP",
        "BOOT_EARLYBOOT",
        "BOOT_DOINITCALLS_PCI",
        "BOOT_DOINITCALLS_VIRTIO",
        "BOOT_DOINITCALLS_ACPI",
        "BOOT_FULL_BOOT",
        "BOOT_REST_INIT",
        "BOOT_VIRTIO_BLK_PROBE",
        "BOOT_START_KERNEL",
        "BOOT_DO_BASIC",
        "BOOT_ACPI_EARLY_INIT"]

initcall_harnesses = [
        "DOINITCALLS_LEVEL_3",
        "DOINITCALLS_LEVEL_4",
        "DOINITCALLS_LEVEL_5",
        "DOINITCALLS_LEVEL_6",
        "DOINITCALLS_LEVEL_7"]

bph_harnesses = [
        "BPH_ACPI_INIT",
        "BPH_VP_MODERN_PROBE",
        "BPH_VIRTIO_CONSOLE_INIT",
        "BPH_P9_VIRTIO_PROBE",
        "BPH_PCI_SUBSYS_INIT",
        "BPH_HANDLE_CONTROL_MESSAGE",
        "BPH_VIRTIO_PCI_PROBE",
        "BPH_PCIBIOS_FIXUP_IRQS"]

user_harnesses = [
        "US_DHCP",
        "US_RESUME_SUSPEND", # Requires input seeds. e.g., from FULL_BOOT
        ]

HARNESSES = boot_harnesses + initcall_harnesses + bph_harnesses + user_harnesses

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

KAFL_CONFIG_DEFAULTS = [
        "abort_time: 2",
        #"timeout: 8",
        #"timeout_soft: 3",
        #"timeout_check: True",
        "trace: True",
        "log_crashes: True",
        #"kickstart: 16",
]

KAFL_CONFIG_HARNESSES = {
        "FULL_BOOT":           ["abort_time: 24", "timeout: 8", "timeout_soft: 3"],
        "DOINITCALLS_LEVEL_6": ["abort_time: 24"],
        "DOINITCALLS_LEVEL_4": ["abort_time: 24"],
        "DO_BASIC":            ["abort_time: 24"],
        }

default_config_options = {"CONFIG_TDX_FUZZ_KAFL_DETERMINISTIC": "y",
        "CONFIG_TDX_FUZZ_KAFL_DISABLE_CPUID_FUZZ": "y",
        "CONFIG_TDX_FUZZ_KAFL_SKIP_IOAPIC_READS": "n",
        "CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO": "n",
        "CONFIG_TDX_FUZZ_KAFL_SKIP_RNG_SEEDING": "y",
        "CONFIG_TDX_FUZZ_KAFL_SKIP_MSR": "n",
        "CONFIG_TDX_FUZZ_KAFL_SKIP_PARAVIRT_REWRITE": "n",
        }

harness_config_options = {
        "BOOT_EARLYBOOT": {"CONFIG_TDX_FUZZ_KAFL_SKIP_PARAVIRT_REWRITE": "n"},
        "BOOT_FULL_BOOT": {"CONFIG_TDX_FUZZ_KAFL_SKIP_PARAVIRT_REWRITE": "y"},
        "BOOT_POST_TRAP": {"CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO": "y", "CONFIG_TDX_FUZZ_KAFL_SKIP_PARAVIRT_REWRITE": "y"},
        "BOOT_DOINITCALLS_VIRTIO": {"CONFIG_TDX_FUZZ_KAFL_VIRTIO": "y"},
        "BOOT_DOINITCALLS_PCI": {"CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO": "y"},
        "BOOT_DOINITCALLS_VIRTIO": {"CONFIG_TDX_FUZZ_KAFL_VIRTIO": "y"},
        "BOOT_START_KERNEL": {"CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO": "y"},
        "CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS": {"CONFIG_TDX_FUZZ_KAFL_SKIP_IOAPIC_READS": "y", "CONFIG_TDX_FUZZ_KAFL_SKIP_ACPI_PIO": "y"},
        "DOINITCALLS_LEVEL_7": {"CONFIG_TDX_FUZZ_KAFL_VIRTIO": "y"},
        "DOINITCALLS_LEVEL_6": {"CONFIG_TDX_FUZZ_KAFL_VIRTIO": "y"},
        "BPH_VIRTIO_CONSOLE_INIT": {"CONFIG_TDX_FUZZ_KAFL_VIRTIO": "y"},
        "US_RESUME_SUSPEND": {"CONFIG_PM": "y", "CONFIG_PM_DEBUG": "y", "CONFIG_PM_ADVANCED_DEBUG": "y", "CONFIG_SUSPEND": "y", "CONFIG_HIBERNATE": "y", "CONFIG_PM_AUTOSLEEP": "n", "CONFIG_PM_WAKELOCKS": "n", "CONFIG_PM_TRACE_RTC": "n", "CONFIG_ACPI_TAD": "n", "CONFIG_FW_CACHE": "y"},
        }

def userspace_script_for_harness(harness):
    if not harness.startswith("US_"):
        return None

    us_name = harness[len("US_"):]
    us_script = os.path.expandvars(f"$BKC_ROOT/bkc/kafl/userspace/harnesses/{us_name}.sh")
    return us_script

def get_kafl_config_boot_params():
    conf_file = os.environ.get("KAFL_CONFIG_FILE")
    with open(conf_file) as conf_yaml_file:
        conf = yaml.load(conf_yaml_file, Loader=yaml.FullLoader)
        default_append = conf.get("qemu_append", "")
        return default_append

def generate_setups(args, harness):
    req_conf = tuple(default_config_options.items())
    harness_options = harness_config_options.get(harness, None)
    if harness_options:
        req_conf = req_conf + tuple(harness_options.items())

    if harness.startswith("BOOT_"):
        basename = harness[len("BOOT_"):]
        req_conf = req_conf + ((f"CONFIG_TDX_FUZZ_HARNESS_{basename}", "y"),)
    elif harness.startswith("DOINITCALLS_LEVEL"):
        level = harness[len("DOINITCALLS_LEVEL_"):]
        req_conf = req_conf + (("CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS", "y"), ("CONFIG_TDX_FUZZ_HARNESS_DOINITCALLS_LEVEL", level),)
    elif harness.startswith("BPH_") or harness.startswith("US_"):
        req_conf = req_conf + (("CONFIG_TDX_FUZZ_HARNESS_NONE", "y"),)
    return req_conf

def select_seed_root(seed_dir, harness):
    harness_dir = os.path.join(seed_dir, harness)
    generic_dir = os.path.join(seed_dir, "generic")

    if os.path.isdir(harness_dir):
        print(f"{harness}: Using harness-specific seeds from {harness_dir}")
        return harness_dir
    if os.path.isdir(generic_dir):
        print(f"{harness}: Using generic seeds from {generic_dir}")
        return generic_dir
    print(f"{harness}: No harness-specific seeds detected, using all of {seed_dir}")
    return seed_dir

def linux_config(args, setup):

    if args.verbose:
        print("Setting linux config overrides:")
        for conf,val in setup:
            print(f"  {conf}={val}")
        print("")

    # Kernel scripts/config fails to correctly update CHOICE options,
    # while kconfig/merge_config.sh uses nonexisting alldefconfig.
    # Best option is to append the custom options. For reproducibility,
    # just copy the template and let build step finalize the .config
    # using e.g "cat a b > .config; make olddefconfig"
    with open(args.configs['linux'], 'w') as f:
        for conf,val in setup:
            f.write(f"{conf}={val}\n")
    shutil.copy(args.template, args.configs['template'])

def kafl_config(args, harness, sharedir):
    yaml=""

    ## add default and harness-specific options (timeout, funky,..)
    yaml = yaml + "\n".join(KAFL_CONFIG_DEFAULTS)
    yaml = yaml + "\n".join(KAFL_CONFIG_HARNESSES.get(harness, [])) + "\n"

    if sharedir:
        yaml += f"sharedir: {sharedir}\n"

    # select seed_dir
    if args.seeds:
        seed_dir = select_seed_root(args.seeds, harness)
        yaml += f"seed_dir: {seed_dir}\n"

    # set any custom boot params
    harness_boot_params = BOOT_PARAM_HARNESSES.get(harness, None)
    if harness_boot_params:
        default_boot_params = get_kafl_config_boot_params()
        full_boot_params = default_boot_params + " " + harness_boot_params
        yaml += f"qemu_append: {full_boot_params}\n"

    if args.verbose and len(yaml) > 0:
        print("kAFL config overrides:")
        for line in yaml.splitlines():
            print(f"  {line}")
        print("")

    with open(args.configs['kafl'], 'w') as f:
        f.write(yaml)

def kafl_sharedir(args, harness):
    SHAREDIR_PATH = os.path.expandvars("$BKC_ROOT/sharedir")
    INITRD_FILE = os.path.expandvars("$BKC_ROOT/initrd.cpio.gz")

    if not os.path.isdir(SHAREDIR_PATH):
        sys.exit(f"Sharedir '{SHAREDIR_PATH}' does not exists. Please do `make sharedir`.")
    if not os.path.isfile(INITRD_FILE):
        sys.exit(f"'{INITRD_FILE}' does not exists. Please do `make initrd.cpio.gz`.")

    userspace_harness_script = userspace_script_for_harness(harness)
    if not userspace_harness_script:
        return None

    if args.verbose:
        print(f"Using sharedir template at {SHAREDIR_PATH}.\nStage 2 init.sh: {userspace_harness_script}")

    sharedir = shutil.copytree(SHAREDIR_PATH, args.configs['sharedir'], dirs_exist_ok=True)
    shutil.copy(userspace_harness_script, os.path.join(sharedir, "init.sh"))
    return sharedir

def process_args(args):
    def parse_as_path(pathname):
        return os.path.abspath(
                os.path.expanduser(
                    os.path.expandvars(pathname)))

    def parse_as_file(filename):
        expanded = parse_as_path(filename)
        if not os.path.exists(expanded):
            raise argparse.ArgumentTypeError("Failed to find file %s (expanded: %s)" % (filename, expanded))
        return expanded

    def parse_as_dir(dirname):
        expanded = parse_as_path(dirname)
        if not os.path.isdir(expanded):
            raise argparse.ArgumentTypeError(f"Failed to find directory {dirname} (expanded: {expanded})")
        return expanded

    # resolve config file template is required, actually
    args.template = parse_as_file(args.template)

    # seeds are not required, but notify in case of config error
    if args.seeds:
        args.seeds = parse_as_dir(args.seeds)

    # prepare files in --output directory or die trying
    args.output = parse_as_path(args.output)
    if os.path.exists(args.output) and not os.path.isdir(args.output):
        raise argparse.ArgumentTypeError(f"Provided output path is not a valid directory: {args.output}")

def parse_args():
    parser = argparse.ArgumentParser(description='kAFL TDX kernel config generator.')
    parser.add_argument('output', metavar='<output>', type=str,
            help='output directory (existing files are overwritten!)')
    parser.add_argument('harness', metavar='<harness>', type=str,
            help='pattern that matches one or more harness configurations (try `list` or `all`)')
    parser.add_argument('--config', '-c', metavar='<file>', dest='template', type=str,
            default="$BKC_ROOT/bkc/kafl/linux_kernel_tdx_guest.config",
            help='kernel .config template (default: $BKC_ROOT/bkc/kafl/linux_kernel_tdx_guest.config)')
    parser.add_argument('--seeds', '-s', metavar='<dir>', type=str,
            help='root seeds directory, containing a subfolder <harness> or "generic"')
    parser.add_argument('--verbose', '-v', action="store_true", help='verbose output')

    #args,_ = parser.parse_known_args()
    args = parser.parse_args()

    # pre-process harness pattern before complaining about output path..
    selected = list()
    if args.harness in ["help", "list"]:
        sys.exit(f"Supported harnesses:\n%s" % pformat(HARNESSES))

    if args.harness == "all":
        selected = HARNESSES
    else:
        for h in HARNESSES:
            if args.harness in h:
                selected.append(h)
    if len(selected) == 0:
        sys.exit(f"Error: unrecognized harness `{args.harness}`.\nSupported patterns:\n%s" % pformat(HARNESSES))
    else:
        args.harness = selected

    # process all other args..
    try:
        process_args(args)
    except (OSError,argparse.ArgumentTypeError) as e:
        sys.exit(f"Error: {e}")
        return None

    return args

def main():
    args = parse_args()
    if not args:
        sys.exit(1)

    if not args.seeds:
        print("No --seed-dir given, continuing without seeds..")

    print(f"Preparing harness(es) at {args.output}:\n%s" % pformat(args.harness))
    for h in args.harness:

        os.makedirs(os.path.join(args.output, h), exist_ok=True)
        args.configs = {
                'template': os.path.join(args.output, h, "linux.template"),
                'linux': os.path.join(args.output, h, "linux.config"),
                'kafl': os.path.join(args.output, h, "kafl.yaml"),
                'sharedir': os.path.join(args.output, h, "sharedir")
                }

        ## test-create destination files in output folder
        #for fname in args.configs.values():
        #    with open(fname, 'w') as f:
        #        f.truncate(0)

        setup = generate_setups(args, h)
        linux_config(args, setup)
        sharedir = kafl_sharedir(args, h)
        kafl_config(args, h, sharedir)

    sys.exit(0)

if __name__ == "__main__":
    main()
