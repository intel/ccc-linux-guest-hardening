#!/usr/bin/env python3

# 
# Copyright (C)  2022  Intel Corporation. 
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

import os
import sys

import time
import glob
import msgpack
import lz4.frame as lz4
import re
import multiprocessing as mp

from operator import itemgetter


import argparse

def read_binary_file(filename):
    with open(filename, 'rb') as f:
        return f.read()

EXIT_IP = 0xffffffffffffffff

# default smatch_warns.txt to use if nothing in $WORKDIR/target/
DEFAULT_SMATCH_FILE = os.path.expandvars("$BKC_ROOT/smatch_warns.txt")

# should reset this between different trace startpoints (-f)
class TraceParser:

    def __init__(self, trace_dir):
        self.trace_dir = trace_dir
        self.known_bbs = set()
        self.known_edges = set()
        self.trace_results = list()
        self.unique_edges = dict()
        self.unique_bbs = set()
        self.callers = dict()
        self.addr2lifu = dict()
        self.line2addr = dict()
        self.func2addr = dict()
        self.smatch_func_map = dict()
        self.smatch_lino_map = dict()
        self.global_back_edges = dict()
        self.seen_edges = set()
        self.func_matches = dict()
        self.lino_matches = dict()

    def print_addr(self, addr, prefix="\t"):
        print("%s%x: %s at %s" % (prefix, addr, self.addr2func(addr), self.addr2line(addr)))


    def is_valid_addr(self, addr):
        return addr != None and addr != 0xffffffffffffffff

    def get_prior_edge_str(self, edge_str):
        return self.global_back_edges[edge_str]

    def get_prior_edge(self, src, dst):
        # search backward through all collected traces - slooow
        edge_str = "%016x,%016x" % (src, dst)
        for prior_edge_str in self.global_back_edges[edge_str]:
            src,dst = prior_edge_str.split(',')
            yield([int(src,16),int(dst,16)])


    def addr2caller(self, addr):
        return self.callers.get(addr, [None])

    def addr2line(self, addr):
        if addr < 0xffffffff00000000:
            return '0'
        return self.addr2lifu[addr][0]

    def addr2func(self, addr):
        if addr < 0xffffffff00000000:
            return 'trace_exit'
        return self.addr2lifu[addr][1]

    def func2addrs(self, func):
        if func == 'trace_exit':
            return [EXIT_IP]
        return self.func2addr[func]

    def func2lines(self, func):
        return set([ self.addr2line(addr) for addr in self.func2addrs(func) ])

    @staticmethod
    def edge_to_str(src,dst):
        return "%016x,%016x" % (src, dst)

    @staticmethod
    def edge_str_to_tuple(edge_str):
        src,dst = edge_str.split(',')
        return [int(src,16),int(dst,16)]

    @staticmethod
    def parse_trace_file(trace_file):
        if not os.path.isfile(trace_file):
            print("Could not find trace file %s, skipping.." % trace_file)
            return None

        bbs = set()
        edges = dict()
        callers = dict()
        with lz4.open(trace_file, 'r') as f:
            for line in f.read().decode(errors="ignore").splitlines():
                try:
                    src,dst,num = line.split(",")
                except:
                    src,dst = line.split(",")
                    num = '1'

                src = int(src,16)
                dst = int(dst,16)
                num = int(num,16)
                edges["%016x,%016x" % (src, dst)] = num
                callers.setdefault(dst, set()).add(src)
                bbs.update({src,dst})

        return {'bbs': bbs, 'edges': edges, 'callers': callers}

    @staticmethod
    def parse_splice_trace_file(trace_file):
        if not os.path.isfile(trace_file):
            print("Could not find trace file %s, skipping.." % trace_file)
            return None
        print("Processing trace file %s.." % trace_file)

        splice_ips = set()
        def do_splice_location(src,dst):
            if src not in splice_ips:
                splice_ips.add(src)
                #print("Splicing at %016x,%016x" % (src,dst))
            return True

        bbs = set()
        edges = dict()
        callers = dict()
        back_edges = dict()
        prev_ip = 0
        last_edge = "%016x,%016x" % (EXIT_IP, EXIT_IP)
        with lz4.open(trace_file, 'r') as f:
            for line in f.read().decode(errors="ignore").splitlines():
                try:
                    src,dst,num = line.split(",")
                except:
                    src,dst = line.split(",")
                    num = '1'

                src = int(src,16)
                dst = int(dst,16)
                num = int(num,16)

                # splice the trace at well-known entry/exit points
                if dst == EXIT_IP:
                    assert(prev_ip == 0)
                    prev_ip = src
                    # insert fake edge
                    prev_ip = (src % 0xffffffff << 32) + 0xffffffff
                    continue
                if prev_ip != 0:
                    assert(src == EXIT_IP)
                    assert(dst != EXIT_IP)
                    if do_splice_location(prev_ip, dst):
                        src = prev_ip
                        prev_ip = 0

                edge_str = "%016x,%016x" % (src, dst)
                edges[edge_str] = edges.get(edge_str, 0) + num
                back_edges.setdefault(edge_str, set()).add(last_edge)
                callers.setdefault(dst, set()).add(src)
                bbs.update({src,dst})
                last_edge = edge_str

        return {'bbs': bbs, 'edges': edges, 'callers': callers, 'back_edges': back_edges}


    def parse_trace_list(self, nproc, input_list):
        trace_files = list()
        timestamps = list()

        for input_file, nid, timestamp in input_list:
            #trace_file = self.trace_dir + "/" + os.path.basename(input_file) + ".lz4"
            trace_file = "%s/fuzz_%05d.lst.lz4" % (self.trace_dir, nid)
            if os.path.exists(trace_file):
                trace_files.append(trace_file)
                timestamps.append(timestamp)
            else:
                print("Could not find trace: %s => %s" % (input_file, trace_file))
        print("Parsing trace: %s => %s" % (input_file, trace_file))

        print("Parsing traces on %d/%d cores..." % (nproc, os.cpu_count()))
        with mp.Pool(nproc) as pool:
            self.trace_results = zip(timestamps,
                                     pool.map(TraceParser.parse_splice_trace_file, trace_files))

    def parse_addr2line(self):
        # parse addr2line DB generated from eu-addr2line -afi < unique_edges.lst
        addr2line = self.trace_dir + "/addr2line.lst"

        if not os.path.exists(addr2line):
            print("Could not find %s." % addr2line)
            sys.exit(1)

        #print("Parsing addr2line dump at %s" % addr2line)
        addr = 0
        with open(addr2line, 'r') as f:
            for line in f.read().splitlines():
                m = re.search("0x([\da-f]+): ([\S]+) at ([\S]+):[0-9]+$", line)
                if m:
                    addr = int(m.group(1),16)
                    func = m.group(2)
                    lino = m.group(3)
                    #print(f"parse addr2line: {line}: '{func}' @ '{lino}'")
                    self.addr2lifu[addr] = (lino, func)
                    self.line2addr.setdefault(lino, list()).append(addr)
                    self.func2addr.setdefault(func, set()).add(addr)
                else:
                    m = re.search(" \(inlined by\) ([\S]+) at ([\S]+):[0-9]+$", line)
                    if m:
                        # addr = previous addr
                        func = m.group(1)
                        lino = m.group(2)
                        #print(f"parse addr2line: {line}: '{func}' @ '{lino}'")
                        self.addr2lifu[addr] = (lino, func)
                        self.line2addr.setdefault(lino, list()).append(addr)
                        self.func2addr.setdefault(func, set()).add(addr)

    def gen_reports(self):

        plot_file = self.trace_dir + "/coverage.csv"
        edges_file = self.trace_dir + "/edges_uniq.lst"

        with open(plot_file, 'w') as f:
            num_bbs = 0
            num_edges = 0
            num_traces = 0
            for timestamp, findings in self.trace_results:
                if not findings: continue

                new_bbs = len(findings['bbs'] - self.unique_bbs)
                new_edges = len(set(findings['edges']) - set(self.unique_edges))
                self.unique_bbs.update(findings['bbs'])
                #self.callers.update(findings['callers'])
                for dst,srcs in findings['callers'].items():
                    self.callers.setdefault(dst, set()).update(srcs)
                edges = findings['edges']
                for edge,num in edges.items():
                    self.unique_edges[edge] = self.unique_edges.get(edge, 0) + num
                back_edges = findings['back_edges']
                for dst,src_set in back_edges.items():
                    self.global_back_edges.setdefault(dst, set()).update(src_set)

                num_traces += 1
                num_bbs += new_bbs
                num_edges += new_edges
                f.write("%d;%d;%d\n" % (timestamp, num_bbs, num_edges))

        with open(edges_file, 'w') as f:
            for edge,num in self.unique_edges.items():
                f.write("%s,%x\n" % (edge,num))

        print(" Processed %d traces with a total of %d BBs (%d edges)." \
                % (num_traces, num_bbs, num_edges))

        print(" Plot data written to %s" % plot_file)
        print(" Unique edges written to %s" % edges_file)

        return


    def callsite_trace_edge(self, edge_str, levels, level=0):

        if level > levels:
            print("%s abort trace at max level %d..)" % ("->", level))
            return True
        if edge_str == "%016x,%016x" % (EXIT_IP,EXIT_IP):
            print("%s exit_ip..)" % ("->"))
            return True

        if edge_str in self.seen_edges:
            #print("%sstop on seen edge..)" % ("|"*level))
            return False

        self.seen_edges.add(edge_str)

        for addr_str in edge_str.split(','):
            addr = int(addr_str,16)
            func = self.addr2func(addr)
            lino = self.addr2line(addr)
            for func in self.smatch_lino_map.get(lino, []):
                print("%s l_match: %24s at %016x, %s, src: %s" % ("->", func, addr, lino, self.addr2line(addr)))
                return True

        any_found = False
        for prior_edge_str in self.get_prior_edge_str(edge_str):
            #print("%sprior edge: %016x,%016x" % ("| "*level, edge[0], edge[1]))
            #self.print_addr(edge[0], prefix="| "*level)
            found = self.callsite_trace_edge(prior_edge_str, levels, level=level+1)
            if found:
                #src = self.edge_str_to_tuple(prior_edge_str)[0]
                #print("%s via: %s - %s" % ("| ", edge_str, self.addr2func(src)))
                pass
            any_found |= found
        return any_found

    def callsite_trace_func(self, func, levels=4):
        # for known IPs in a function, build the unique set of caller IPs and trace them
        addrs = self.func2addrs(func)
        for addr in addrs:
            #print("trace_by_func(%s) -> %016x" % (func, addr))
            for src in self.addr2caller(addr):
                if src:
                    edge_str = "%016x,%016x" % (src, addr)
                    self.callsite_trace_edge(edge_str, levels, level=1)

    def print_callers(self, func, levels=4, level=0, seen_callers=set()):
        callers = set()

        try:
            self.func2addrs(func)
        except KeyError:
            print("Error: Could not find »%s« in addr2line data." % func)
            return

        # get possible entry sites - also includes sites that return to us :-/
        for addr in self.func2addrs(func):
            for caller in self.addr2caller(addr):
                if self.is_valid_addr(caller):
                    callers.add(caller)

        callers -= seen_callers
        seen_callers.update(callers)

        if callers:
            self.print_addr(addr, prefix="| "*level)
            if level < levels:
                for func in sorted(set(self.addr2func(addr) for addr in callers)):
                    self.print_callers(func, levels, level=level+1, seen_callers=seen_callers)


    def collect_callers(self, func, levels=4, level=0, seen_callers=set()):
        callers = set()

        try:
            self.func2addrs(func)
        except KeyError:
            print("Error: Could not find »%s« in addr2line data." % func)
            return

        # get possible entry sites - also includes sites that return to us :-/
        for addr in self.func2addrs(func):
            for caller in self.addr2caller(addr):
                if self.is_valid_addr(caller):
                    callers.add(caller)

        callers -= seen_callers
        seen_callers.update(callers)

        result = set(callers)
        if callers:
            #self.print_addr(addr, prefix="| "*level)
            if level < levels:
                for func in sorted(set(self.addr2func(addr) for addr in callers)):
                    result |= self.collect_callers(func, levels, level=level+1, seen_callers=seen_callers)
        return result


def kafl_workdir_iterator(work_dir):
    input_id_time = list()
    start_time = time.time()
    for stats_file in glob.glob(work_dir + "/slave_stats_*"):
        if not stats_file:
            return None
        slave_stats = msgpack.unpackb(read_binary_file(stats_file), raw=False, strict_map_key=False)
        start_time = min(start_time, slave_stats['start_time'])

    # enumerate inputs from corpus/ and match against metainfo in metadata/
    # TODO: Tracing crashes/timeouts has minimal overall improvement ~1-2%
    # Probably want to make this optional, and only trace a small sample
    # of non-regular payloads by default?
    for input_file in glob.glob(work_dir + "/corpus/[ctrk]*/*"):
        if not input_file:
            return None
        input_id = os.path.basename(input_file).replace("payload_", "")
        meta_file = work_dir + "/metadata/node_{}".format(input_id)
        metadata = msgpack.unpackb(read_binary_file(meta_file), raw=False, strict_map_key=False)

        seconds = metadata["info"]["time"] - start_time
        nid = metadata["id"]

        input_id_time.append([input_file, nid, seconds])

    return input_id_time

def get_inputs_by_time(data_dir):
    # check if data_dir is kAFL or AFL type, then assemble sorted list of inputs/input IDs over time
    if (os.path.exists(data_dir + "/fuzzer_stats") and
        os.path.exists(data_dir + "/fuzz_bitmap") and
        os.path.exists(data_dir + "/plot_data") and
        os.path.isdir(data_dir + "/queue")):
            input_data = afl_workdir_iterator(data_dir)

    elif (os.path.exists(data_dir + "/stats") and
          os.path.isdir(data_dir + "/corpus/regular") and
          os.path.isdir(data_dir + "/metadata")):
            input_data = kafl_workdir_iterator(data_dir)
    else:
        print("Unrecognized target directory type «%s». Exit." % data_dir)
        sys.exit()

    # timestamps may be off slightly but payload IDs are strictly ordered by kAFL master
    input_data.sort(key=itemgetter(2))
    return input_data

def graceful_exit(workers):
    for w in workers:
        w.terminate()

    print("Waiting for Worker to shutdown...")
    time.sleep(1)

    while len(workers) > 0:
        for w in workers:
            if w and w.exitcode is None:
                print("Still waiting on %s (pid=%d)..  [hit Ctrl-c to abort..]" % (w.name, w.pid))
                w.join(timeout=1)
            else:
                workers.remove(w)

def main():

    def default_nproc():
        return int(max(4, os.cpu_count()/4))

    """
    Parse smatch report to extract function names and associated file/line info
    Returns list of tuples: <func, file:line>
    """
    def parse_smatch_file(smatch_file):
        #func2lino = dict()
        #lino2func = dict()
        lino2msg = dict()
        with open(smatch_file, "r") as f:
            for line in f.read().splitlines():
                m = re.search("(\S+:[0-9]+)\s(\S+)\(\)", line)
                if not m:
                    continue
                lino = m.group(1)
                # func = m.group(2)

                #func2lino.setdefault(func, set()).add(lino)
                #lino2func[lino] = func
                lino2msg[lino] = line
        return lino2msg


    parser = argparse.ArgumentParser(description='kAFL Trace Processing.')
    parser.add_argument('work_dir', metavar='<work_dir>', type=str,
            help='target workdir with trace files in /traces/')
    parser.add_argument('-f', '--func', metavar='<func>', type=str,
            help='function to search for')
    parser.add_argument('-p', metavar='<n>', type=int, default=default_nproc(),
            help='number of threads')
    parser.add_argument('-l', metavar='<n>', type=int, default=2,
            help='max call depths to search')

    args = parser.parse_args()

    trace_dir = args.work_dir + "/traces"

    if not os.path.isdir(trace_dir):
        sys.exit(f"Error: Could not find {trace_dir}.")

    target_smatch_file = args.work_dir + "/target/smatch_warns.txt"
    if os.path.exists(target_smatch_file):
        smatch_file = target_smatch_file
    elif os.path.exists(DEFAULT_SMATCH_FILE):
        smatch_file = DEFAULT_SMATCH_FILE
    else:
        sys.exit(f"Error: Could not find smatch report at {target_smatch_file} or {DEFAULT_SMATCH_FILE}.")

    # TraceParse is not really used, just borrowing addr2line parser..
    traces = TraceParser(trace_dir)
    traces.parse_addr2line()

    smatch_map = parse_smatch_file(smatch_file)

    for lino in smatch_map.keys():
        addrs = traces.line2addr.get(lino, None)
        if addrs:
            print("%s" % (smatch_map[lino]))
    # debug info can be wrong, e.g. addr2line may resolve io_apic.c:310 to line 311 instead
    # try to increment/decrement to find a possible hit?


if __name__ == "__main__":
    main()
