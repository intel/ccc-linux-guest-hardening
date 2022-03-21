#!/usr/bin/env python3

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

import os, sys, string, re, argparse


def main(args):
    input_analyzed = args.input_analyzed
    input_new = args.input_new
    output_file = args.f

    if not os.path.isfile(input_new):
        print(f"New input file {input_new} does not exists", file=sys.stderr)
        exit(1)
    if not os.path.isfile(input_analyzed):
        print(f"Analyzed input file {input_analyzed} does not exists", file=sys.stderr)
        exit(1)
    if os.path.isfile(output_file):
        print(f"Output file {output_file} already exists. Please remove the file first or use -f flag!", file=sys.stderr)
        exit(1)

    with open(input_analyzed, 'r') as fanalysed:
            data_analyzed = fanalysed.read()
    result_list_analyzed = data_analyzed.split(';')

    with open(input_new, 'r') as fmsr:
            data_new = fmsr.read()
    result_list_new = data_new.split(';')

    tmp_new_file = output_file + ".tmp.new"
    tmp_old_file = output_file + ".tmp.old"

    with open(tmp_new_file, 'w') as foutput_new:
            with open(tmp_old_file, 'w') as foutput_old:
                    with open(output_file, 'w') as foutput_analyzed:
                            for result_new in result_list_new:
                                    result_new = result_new.strip()
                                    if result_new == "":
                                            continue
                                    #print ("Input result is " + result_new)
                                    found = 0;
                                    path_new = result_new.split(':')[0];
                                    path_new = path_new.strip()
                                    #print ("path_new is  " + path_new + "\n")
                                    result_id_new = re.search(r"\{([A-Za-z0-9_]+)\}", result_new)
                                    if (not result_id_new):
                                            continue
                                    #print ("result_id_new is  " + result_id_new.group(1) + "\n")
                                    func_name_new = result_new.split(':')[1].split(' ')[1];
                                    for result_analyzed in result_list_analyzed:
                                            result_analyzed = result_analyzed.strip()
                                            if result_analyzed == "":
                                                    continue
                                            #print ("result_analyzed is " + result_analyzed + "\n")
                                            if (result_new in result_analyzed):
                                                    found = 1;
                                                    if args.t:
                                                        foutput_old.write(result_analyzed + ";\n")
                                                    foutput_analyzed.write(result_analyzed + ";\n")
                                                    break;
                                            path_analyzed = result_analyzed.split(':')[0]
                                            tmp = result_analyzed.split('\n')[0];
                                            if (tmp.find('\t') == -1):
                                                    status_analyzed = ""
                                            else:
                                                    status_analyzed = tmp.split('\t')[0].strip();
                                            #print ("status_analyzed is  " + status_analyzed + "\n")
                                            if (len(result_analyzed.split(':')[0].split('\t')) > 1):
                                                    path_analyzed = result_analyzed.split(':')[0].split('\t')[1]
                                            path_analyzed = path_analyzed.strip()
                                            #print ("path_analyzed is  " + path_analyzed + "\n")
                                            result_id_analyzed = re.search(r"\{([A-Za-z0-9_]+)\}", result_analyzed)
                                            if (not result_id_analyzed):
                                                    continue
                                            #print ("result_id_analyzed is  " + result_id_analyzed.group(1) + "\n")
                                            if (len(result_analyzed.split(':')) < 2):
                                                    continue
                                            func_name_analyzed = result_analyzed.split(':')[1].split(' ')[1];
                                            comment_analyzed = "";
                                            if (len(result_analyzed.split('\n\t')) > 2):
                                                    comment_analyzed = re.findall(r'\[.*?\]', result_analyzed.split('\n\t')[2])
                                            #if comment_analyzed:
                                                    #print ("comment_analyzed is  " + comment_analyzed[0] + "\n")
                                            if ((path_analyzed == path_new)
                                            and (result_id_analyzed.group(1) == result_id_new.group(1))
                                            and (func_name_analyzed == func_name_new)):
                                                    found = 1;
                                                    if status_analyzed:
                                                            #print ("result_new is  " + result_new + "\n")
                                                            result = status_analyzed + "\t" + result_new
                                                    else:
                                                            result = result_new
                                                    if comment_analyzed:
                                                            result = result + "\n\t" + comment_analyzed[0]
                                                    result = result + ";\n"
                                                    if args.t:
                                                        foutput_old.write(result)
                                                    foutput_analyzed.write(result)
                                                    break;
                                    if (not found):
                                        if args.t:
                                            foutput_new.write(result_new + ";\n")
                                        foutput_analyzed.write(result_new + ";\n")
    if not args.t:
        # Clean up tmp files
        os.remove(tmp_new_file)
        os.remove(tmp_old_file)

    print(f"Wrote output to file '{output_file}'", file=sys.stderr)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Smatch result transfer script. Transfer previous audit results to a new kernel version.')
    parser.add_argument('input_analyzed', metavar='<input_analyzed>', type=str, help='File containing already analyzed smatch results which you want to transfer to a new version')
    parser.add_argument('input_new', metavar='<input_new>', type=str, help='New input file / transfer target (smatch_warns.txt). Generate using path_to_smatch/smatch_scripts/test_kernel.sh')
    parser.add_argument('-f', metavar='<output_file>', type=str, default="smatch_warns.txt.analyzed",
            help=f'Store output to specified file')
    parser.add_argument('-t', action="store_true",
            help=f'Store temporary/ auxiliary files (.tmp.new, .tmp.old). Useful for debugging.')
    args = parser.parse_args()
    main(args)
