#!/usr/bin/env python3
#
#
# Copyright (C)  2023  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and
# your use of them is governed by the express license under which they were
# provided to you ("License"). Unless the License provides otherwise, you may
# not use, modify, copy, publish, distribute, disclose or transmit this software
# or the related documents without Intel's prior written permission.  This
# software and the related documents are provided as is, with no express or
# implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT
#
#
# This script takes an addr2line type of kAFL trace dump and outputs a JSON that adheres
# to the Trace Event Format for utilizing the trace visualization from Catapult Trace-viewer.

import os
import sys
import argparse
import json
from json import JSONEncoder



time_interval = 10
flag_verbose = False

# anchor function and anchor srcs are identifiers for a special routine
# Without considered the whole CS routine, we start with one function:
# finish_task_switch() called in the context of the next running thread
anchor_funcs = ["finish_task_switch"]

# For now, avoid ID the entire CS routine
anchor_srcs = ["parser4tv"]
# anchor_srcs = ["/kernel/sched/"]

# basic functions identifiers
# not include utility calls and other functions from kernel
func_kafl_agent = "kafl-agent.c"
func_kasan = "kasan"


class TraceArgs:
    def __init__(self, line):
        (left_half, right_half) = line.split(" at ")
        if " (inlined by) " in left_half:
            self.vma = "inlined"
            self.func_name = left_half.replace(" (inlined by) ", '')
        else:
            self.vma = left_half.split(': ')[0]
            self.func_name = left_half.split(': ')[1]
        self.src_path = right_half.split(':')[0]
        self.code_loc = right_half.replace(self.src_path, '').replace("\n", '')

    def __str__(self):
        return "\tvma:      {}\n\tsrc_path: {}\n\tfunc_name:{}\n\tcode_loc: {}\n".format(
            self.vma, self.src_path, self.func_name, self.code_loc)


class TraceEntry:
    def __init__(self, line, ts, pid, tid, dur=time_interval, cat="PERF", ph="X", ):
        self.args = TraceArgs(line)
        self.name = self.args.func_name
        self.cat = cat
        self.ph = ph
        self.ts = ts
        self.pid = pid
        self.tid = tid
        self.dur = time_interval

    def is_kafl(self):
        if "kafl" in self.args.src_path:
            return True
        return False

    def is_kasan(self):
        if "kasan" in self.args.src_path:
            return True
        return False

    def is_context_switching(self):
        for func in anchor_funcs:
            if func == self.name:
                return True
        for src in anchor_srcs:
            if src in self.args.src_path:
                return True
        return False

    def merge_trace(self, nt):
        prev_cloc_seq = self.args.code_loc
        if len(prev_cloc_seq.split(" -> ")) == 1:
            if self.args.code_loc != nt.args.code_loc:
                self.args.code_loc = prev_cloc_seq + " -> " + nt.args.code_loc
        else:
            if prev_cloc_seq.split(' -> ')[-1] != nt.args.code_loc:
                self.args.code_loc = prev_cloc_seq + " -> " + nt.args.code_loc
        self.dur += time_interval

    def update_task_id(self, pt):
        self.tid = pt.tid
        self.pid = pt.pid

    def get_task_id(self):
        return self.pid

    def set_pid(self, pid):
        self.pid = pid

    def set_tid(self, tid):
        self.tid = tid

    @staticmethod
    def is_same_function(trace_prev, trace_curr):
        if trace_prev.name == trace_curr.name and trace_prev.args.src_path == trace_curr.args.src_path:
            return True
        return False


class TraceEntryEncoder(JSONEncoder):
    def default(self, o):
        return o.__dict__


def json_line_out(args, t):
    output_name = args.output_name
    if args.readable_json:
        # layered, human readable
        event_json_str = json.dumps(t, indent=4, cls=TraceEntryEncoder)
    else:
        event_json_str = json.dumps(t, cls=TraceEntryEncoder)  # single line
    with open(output_name, 'a') as outfile:
        outfile.write(event_json_str + ',\n')


def gen_json_taskview(args):

    flag_verbose = args.v
    input_addr2lst = args.input_addr2lst
    output_name = args.output_name
    rest_to_process = args.stop_at

    if not os.path.isfile(input_addr2lst):
        print(f"Error: input file {input_addr2lst} does not exist.",
              file=sys.stderr)
        exit(1)
    if os.path.isfile(output_name) and not args.force_overwrite:
        print(f"Error: The output file {output_name} already exists. Add --force_overwrite to overwrite.",
              file=sys.stderr)
        exit(1)

    with open(output_name, 'w') as outfile:
        outfile.write('[\n')

    event_ts = 0

    pid_cs = 0
    pid_nkf = 1

    pid_curr = pid_nkf
    with open(input_addr2lst, 'r') as infile:
        lst_t = []
        flag_prev_cs = False
        for line in infile:

            rest_to_process -= 1

            # Currently, only one type of misformat is observed and matters
            # Thus, focus on it for cheaper cost
            try:
                line_halves = line.split(" at ")
                (left_half, right_half) = line.split(" at ")
            except ValueError:
                print(
                    "\n[Error] Skipping an improperly formatted entry (lack of 'at'):")
                print("[Error] \t", line)
                continue

            t = TraceEntry(line, event_ts, 0, 0)

            if t.is_context_switching():
                pid_curr = pid_cs
                t.set_pid(pid_curr)
                t.set_tid(pid_curr)

                # the process to match and merge this functioni call
                if not lst_t:
                    lst_t.append(t)
                    flag_prev_cs = True
                elif len(lst_t) == 1:
                    if TraceEntry.is_same_function(lst_t[0], t):
                        lst_t[0].merge_trace(t)
                        flag_prev_cs = True
                    else:
                        json_line_out(args, lst_t.pop(0))
                        lst_t.append(t)
                        flag_prev_cs = True
            else:
                if not lst_t:
                    if flag_prev_cs:
                        pid_nkf += 1
                        flag_prev_cs = False
                    pid_curr = pid_nkf
                    t.set_pid(pid_curr)
                    t.set_tid(pid_curr)
                    lst_t.append(t)
                elif len(lst_t) == 1:
                    if TraceEntry.is_same_function(lst_t[0], t):
                        lst_t[0].merge_trace(t)
                    else:
                        json_line_out(args, lst_t.pop(0))
                        if flag_prev_cs:
                            pid_nkf += 1
                            flag_prev_cs = False
                        pid_curr = pid_nkf
                        t.set_pid(pid_curr)
                        t.set_tid(pid_curr)
                        lst_t.append(t)

            if flag_verbose:
                print("-------- Trace Entry info: --------")
                print("pid_curr = ", pid_curr)
                attrs = vars(t)
                print(', '.join("%s: %s" % item for item in attrs.items()))

            event_ts += time_interval  # update the timestamp

            if rest_to_process == 0:
                print("\Parsing aborted. Total lines processed:", args.stop_at)
                break

        # print out current buffer
        if lst_t:
            for t_left in lst_t:
                json_line_out(args, t_left)

        for task_id in range(0, pid_nkf):
            event_json_str = json.dumps({
                "cat": "__metadata",
                "name": "native_kernel_task"+str(task_id),
                "args":  '{"name": "native_kernel_task"'+str(task_id)+'}',
                "pid": task_id,
                "tid": task_id,
            }
            )
            with open(output_name, 'a') as outfile:
                outfile.write(event_json_str + ',\n')

        # Remove the comma from the last entry.
        # This works fine for single-byte encodings.
        # seek back enough bytes from the end to account for a single codepoint
        # if using a multi-byte encoding (e.g., UTF-16 or UTF-32)
        with open(output_name, 'rb+') as outfile:
            outfile.seek(-2, os.SEEK_END)
            outfile.truncate()

        with open(output_name, 'a') as outfile:
            outfile.write('\n]')

    print("\nDone parsing and converting the add2lst. Json file name: ", output_name)


def gen_json_flat(args):
    print("[flat view] gen json withou reflect different threads")

    flag_verbose = args.v
    input_addr2lst = args.input_addr2lst
    output_name = args.output_name
    rest_to_process = args.stop_at

    if not os.path.isfile(input_addr2lst):
        print(f"Error: input file {input_addr2lst} does not exist.",
              file=sys.stderr)
        exit(1)
    if os.path.isfile(output_name) and not args.force_overwrite:
        print(f"Error: The output file {output_name} exists. Add --force_overwrite to overwrite.",
              file=sys.stderr)
        exit(1)

    with open(output_name, 'w') as outfile:
        outfile.write('[\n')

    event_ts = 0

    with open(input_addr2lst, 'r') as infile:
        lst_t = []
        for line in infile:
            rest_to_process -= 1
            
            # Currently, only one type of misformat is observed and matters
            # Thus, focus on it for cheaper cost
            try:
                line_halves = line.split(" at ")
                (left_half, right_half) = line.split(" at ")
            except ValueError:
                print(
                    "\n[Error] Skipping an improperly formatted entry (lack of 'at'):")
                print("[Error] \t", line)
                continue

            t = TraceEntry(line, event_ts, 0, 0)

            # the process to match and merge this functioni call
            if not lst_t:
                lst_t.append(t)
            elif len(lst_t) == 1:
                if TraceEntry.is_same_function(lst_t[0], t):
                    lst_t[0].merge_trace(t)
                else:
                    json_line_out(args, lst_t.pop(0))
                    lst_t.append(t)

            if flag_verbose:
                print("-------- CurrentTrace Entry info: --------")
                attrs = vars(t)
                print(', '.join("%s: %s" % item for item in attrs.items()))

            event_ts += time_interval  # update the timestamp

            if rest_to_process == 0:
                print("\n[Parsing aborted] Total lines processed:", args.stop_at)
                break

        # print out current buffer
        if lst_t:
            for t_left in lst_t:
                json_line_out(args, t_left)

        for task_id in range(0, 1):
            event_json_str = json.dumps({
                "cat": "__metadata",
                "name": "execution_flow"+str(task_id),
                "args":  '{"name": "execution_flow"'+str(task_id)+'}',
                "pid": task_id,
                "tid": task_id,
            }
            )
            with open(output_name, 'a') as outfile:
                outfile.write(event_json_str + ',\n')

        # Remove the comma from the last entry.
        # This works fine for single-byte encodings.
        # seek back enough bytes from the end to account for a single codepoint
        # if using a multi-byte encoding (e.g., UTF-16 or UTF-32)
        with open(output_name, 'rb+') as outfile:
            outfile.seek(-2, os.SEEK_END)
            outfile.truncate()

        with open(output_name, 'a') as outfile:
            outfile.write('\n]')

    print("\nDone parsing and converting the add2lst. Json file name: ", output_name)


def extract_trace(args):
    flag_verbose = args.v
    input_addr2lst = args.input_addr2lst
    output_lst = input_addr2lst.replace(
        ".lst", "{}.lst".format("_f"+str(args.extract_lines)))
    rest_to_process = args.extract_lines

    if not os.path.isfile(input_addr2lst):
        print(f"Error: input file {input_addr2lst} does not exist.",
              file=sys.stderr)
        exit(1)
    if os.path.isfile(output_lst) and not args.force_overwrite:
        print(
            f"Error: The output file {output_lst} exists. Add --force_overwrite to overwrite.",
             file=sys.stderr)
        exit(1)

    with open(output_lst, 'w') as outfile:

        with open(input_addr2lst, 'r') as infile:
            for line in infile:
                rest_to_process -= 1
                outfile.write(line)

                if rest_to_process == 0:
                    print("\Parsing stopped. Total lines processed:",
                          args.extract_lines)
                    break
    print("\nDone extracting the original addr2lst. New lst file name: ", output_lst)


def main(args):
    global time_interval
    time_interval = args.time_interval

    if args.extract_lines == 0:
        if args.task_view:
            gen_json_taskview(args)
        else:
            gen_json_flat(args)
    else:
        extract_trace(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='kAFL trace based addr2line dump converter script.\n'
        'Transfer addr2line list to a Trace-viwer compilable JSON format')

    parser.add_argument('input_addr2lst', metavar='<input_addr2lst>', type=str,
                        help='input file: addr2line trace list file')
    parser.add_argument('-o', '--output_name', metavar='<output_name>', type=str,
                        default="trace_out.json",
                        help='specify output name. default: trace_out.json / [*]_f[#].lst -e mode')
    parser.add_argument('-s', '--stop_at', metavar='<stop_at>', type=int, default=0,
                        help='hint the parser to stop processing after N lines')
    parser.add_argument('-e', '--extract_lines', metavar='<extract_lines>', type=int,
                        default=0, help='extract first N line of traces to a separate trace list')
    parser.add_argument('--time_interval', metavar='<time_interval>', type=int, default=10,
                        help='set time interval for the basic unit, default: 10 us')
    parser.add_argument('-f', '--force_overwrite', action="store_true",
                        help='force overwrite existing output files')
    # parser.add_argument('--no-kasan', action="store_true", help='ignore all kasan related traces')
    # parser.add_argument('--no-kafl', action="store_true", help='ignore all kafl related traces')
    parser.add_argument('-v', action="store_true", help='toggle verbose')
    parser.add_argument('--task_view', action="store_true",
                        help='experimental: try to infer context switch to differentiate tasks')
    parser.add_argument('--readable_json', action="store_true",
                        help='enable layered json, more human readable format')

    args = parser.parse_args()
    main(args)