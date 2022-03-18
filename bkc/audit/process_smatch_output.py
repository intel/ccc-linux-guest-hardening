#!/usr/bin/env python3

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#

import os, sys, string, re, argparse

smatch_pattern_name = "check_host_input"

tdx_allowed_drivers = ["drivers/virtio", "drivers/block/virtio_blk.c", "drivers/net/virtio_net.c", "drivers/char/virtio_console.c", "drivers/acpi", "drivers/char/hpet.c", "drivers/pci", "drivers/rtc/rtc-mc146818-lib.c", "drivers/firmware/qemu_fw_cfg.c", "drivers/net/tun.c", "drivers/net/tap.c", "drivers/firmware/efi"]

def main(args):
    input_file = args.input_file
    output_file = args.output_file
    print("Input file is " + input_file, file=sys.stderr)

    if not os.path.isfile(input_file):
        print(f"Input file {input_file} does not exists", file=sys.stderr)
        exit(1)

    if os.path.isfile(output_file):
        print(f"Output file {output_file} already exists. Please delete this file first!", file=sys.stderr)
        exit(1)

    with open(input_file, 'r') as finput:
            data = finput.read() #read the whole file and save to variable data
    result_lines = data.split('\n')
    data_clean = ""
    for line in result_lines:
            if (not re.search(r"\{([A-Za-z0-9_]+)\}", line)) and (smatch_pattern_name not in line):
                    continue		
            data_clean = data_clean + line + "\n"
    #print("data_clean: " + data_clean)
    result_list = data_clean.split(';')
    results_seen = set()
    with open(output_file, 'w') as foutput_warn:
            for result in result_list:
                    if result == "" or result == "\n" or result == ";":
                            continue
                    if result in results_seen:  # a duplicate
                            continue
                    if ("../" in result):
                            continue # basically dropping all relative paths now since they are duplicates
                    results_seen.add(result)
                    #print ("Result is " + result)
                    found = 0
                    if result.startswith("\nsound/"):
                            continue
                    if result.startswith("\nsamples/"):
                            continue
                    if result.startswith("\ndrivers/") or result.startswith("\n./drivers/"):
                            if ("drivers/pci/controller/" in result):
                                    continue;
                            for x in tdx_allowed_drivers:
                                    if (x in result):
                                            found = 1
                                            break
                            if (found == 0):
                                    continue
                    foutput_warn.write(result + ";")

    print(f"Wrote data to '{output_file}'", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Smatch result filter script. Filters out excluded subsystems from the smatch report.')
    parser.add_argument('input_file', metavar='<input_file>', type=str, help='Smatch report file (smatch_warns.txt) to be filtered.')
    parser.add_argument('-f', '--output_file', metavar='<output_file>', type=str, default="smatch_warns.txt.filtered",
            help=f'Store output to specified file')
    args = parser.parse_args()
    main(args)
