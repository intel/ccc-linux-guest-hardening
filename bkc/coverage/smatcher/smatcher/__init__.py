#!/usr/bin/env python3

#
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

import os
import sys
import argparse
import re
import pickle
from itertools import groupby

SMATCH_PATH = os.environ.get("SMATCH_PATH", os.path.expanduser("~/tdx/smatch"))
smdb_available = False

# smatch smdb.py - broken
#try:
#    sys.path.insert(0, os.path.join(SMATCH_PATH, "smatch_data/db"))
#    import smdb
#    smdb_available = True
#except Exception:
#    smdb_available = False

__author__ = "Sebastian Österlund <sebastian.osterlund@intel.com>"
__email__ = "sebastian.osterlund@intel.com"
__version__ = "0.1.0"
__license__ = "MIT"

SYMBOL_COV = "+"
SYMBOL_NOT_COV = "-"
SYMBOL_PARTIAL_COV = "/"
GLOBAL_DB_FILE = os.path.expanduser("~/tdx/bkc/kafl/.global_cov.db")
SMATCH_REACHABILITY_DB_FILE = "smatch_db.sqlite"
IND = "  "

SMATCH_CAT_CONCERN = "concern"
SMATCH_CAT_SAFE = "safe"
SMATCH_CAT_EXCLUDED = "excluded"
SMATCH_CAT_WRAPPER = "wrapper"
SMATCH_CAT_UNCLASSIFIED = "unclassified"
SMATCH_CAT_TRUSTED = "trusted"

LINECOV_FILES = ["traces/linecov.lst", "traces/smatch_match_rust.lst",
                 "traces/smatch_match.lst", "traces/addr2line.lst"]

KERNEL_ANALYSIS_START_FUNCS = ["start_kernel", "kernel_init"]


# Returns entries in the form
# (classification, line, function)
def parse_smatch_file(fname):
    entries = set()
    with open(fname, "r") as fh:
        s = fh.read()
        # Get classified entries
        m = re.findall("(\S+)\t(\S+:[0-9]+) (\S+)\(\)", s)
        for c, l, f in m:
            entries.add((c, os.path.normpath(l.strip('./')), f))
        # Get unclassified entries
        m = re.findall("^(\S+:[0-9]+) (\S+)\(\)", s, re.M)
        for l, f in m:
            if not f == "(null)":
                entries.add((SMATCH_CAT_UNCLASSIFIED,
                            os.path.normpath(l.strip('./')), f))
    return entries


def parse_line_coverage_file(fname):
    lines = set()
    with open(fname, "r") as fh:
        try:
            s = fh.read()
            m = re.findall("[\w./]+:[0-9]+", s)
            for l in m:
                lines.add(os.path.normpath(l.strip('./')))
        except UnicodeDecodeError as e:
            print(f"Error decoding file {fname}: {e}", file=sys.stderr)
            pass
    return lines


def try_find_smatch_file(args, input_item):
    if args.smatch:
        if not os.path.isfile(args.smatch):
            print(
                f"Could not find provided smatch file '{args.smatch}'.", file=sys.stderr)
            sys.exit(1)
        return args.smatch

    # Treat as linecov input
    if os.path.isfile(input_item) and args.smatch is None:
        # TODO: add default global/ cwd smatch file??
        print("Could not auto-detect smatch file. Please set '--smatch' parameter", file=sys.stderr)
        sys.exit(1)

    # Treat as kAFL workdir
    work_dir = input_item
    smatch_file = os.path.join(work_dir,
                               "target/smatch_warns.txt_results_analyzed")
    if os.path.isfile(smatch_file):
        return smatch_file

    print(f"Could not find '{smatch_file}'. Trying others...",
          file=sys.stderr)

    smatch_file = os.path.join(work_dir, "target/smatch_warns.txt")
    if os.path.isfile(smatch_file):
        return smatch_file

    print(f"Could not find smatch file '{smatch_file}'. Giving up.",
          file=sys.stderr)
    if not args.ignore_errors:
        sys.exit(1)


def try_get_coverage(args, input_item):
    cov = set()
    existing_files = 0

    # Interpret as a single coverage input file
    if os.path.isfile(input_item):
        return parse_line_coverage_file(input_item)

    # The input item is a workdir
    if not os.path.isdir(input_item):
        print(f"Provided path '{input_item}' is not a valid kAFL workdir",
              file=sys.stderr)
        if not args.ignore_errors:
            sys.exit(1)

    work_dir = input_item
    for f in LINECOV_FILES:
        line_coverage_path = os.path.join(work_dir, f)
        if not os.path.isfile(line_coverage_path):
            print(f"Could not find coverage file '{line_coverage_path}'. Trying next...",
                  file=sys.stderr)
            continue
        existing_files += 1
        if args.combine_cov_files:
            cov |= parse_line_coverage_file(line_coverage_path)
        else:
            return parse_line_coverage_file(line_coverage_path)

    if existing_files == 0:
        print(f"Could not find and of the coverage files '{LINECOV_FILES}'.\n"
              "Please make sure one exists, or provide an alternative file with --cov.",
              file=sys.stderr)
        if not args.ignore_errors:
            sys.exit(1)
    return cov


def start(args):
    covered = set()
    if args.load:
        with open(args.db_file, "rb") as fh:
            covered |= pickle.load(fh)
            print("Loaded %d lines from db" % len(covered), file=sys.stderr)

    smatch_set = set()
    for input_item in args.input_items:
        cov = try_get_coverage(args, input_item)
        smatch_file = try_find_smatch_file(args, input_item)
        if smatch_file is None:
            continue
        sm = parse_smatch_file(smatch_file)
        smatch_set |= sm
        sm_map = dict()
        for (c, l, f) in sm:
            e = sm_map.get(l, set())
            e.add((c, l, f))
            sm_map[l] = e

        for line in cov:
            e = sm_map.get(line, set())
            if len(e) > 0:
                covered |= e
    if args.save:
        # Load DB, so we merge the coverage
        if os.path.isfile(args.db_file):
            with open(args.db_file, "rb") as fh:
                covered |= pickle.load(fh)
        with open(args.db_file, "wb+") as fh:
            pickle.dump(covered, fh)

    not_covered = smatch_set - covered
    covered_funcs = set([f for c, l, f in covered])
    not_covered_funcs = set([f for c, l, f in not_covered]) - covered_funcs
    partially_covered_funcs = set([f for c, l, f in not_covered]) & covered_funcs

    print("##############")
    print("SUMMARY STATS:")
    print("##############")
    print(IND + "Covered funcs: {}".format(len(covered_funcs)))
    print(IND + "Not covered funcs: {}".format(len(not_covered_funcs)))
    print(IND + "Partially covered funcs: {}".format(len(partially_covered_funcs)))
    #print(IND + "Line coverage input: {}".format(len(cov)))
    print(IND + "Covered smatch entries: {}".format(len(covered)))
    print(IND + "Not covered smatch entries: {}".format(len(not_covered)))
    cov_non_excl = []
    not_cov_non_excl = []
    for cl in [SMATCH_CAT_SAFE, SMATCH_CAT_CONCERN, SMATCH_CAT_WRAPPER, SMATCH_CAT_EXCLUDED, SMATCH_CAT_TRUSTED, SMATCH_CAT_UNCLASSIFIED]:
        covered_class = list(filter(lambda e: e[0] == cl, covered))
        not_covered_class = list(filter(lambda e: e[0] == cl, not_covered))
        if cl not in ["excluded", "wrapper", "unclassified"]:
            cov_non_excl.extend(covered_class)
            not_cov_non_excl.extend(not_covered_class)
        cov_pctg = 100 * len(covered_class)/(len(covered_class) + len(not_covered_class)) if len(covered_class) + len(not_covered_class) > 0 else 0

        cl_covered_funcs = set(map(lambda e: e[2], covered_class))
        cl_not_covered_funcs = set(map(lambda e: e[2], filter(lambda e: e[0] == cl, not_covered))) - cl_covered_funcs
        cov_pctg_funcs = 100 * len(cl_covered_funcs)/(len(cl_covered_funcs) + len(cl_not_covered_funcs)) if len(cl_covered_funcs) + len(cl_not_covered_funcs) > 0 else 0
        funcs_stats_str = "functions {}/{} => {:.2f}%".format(len(cl_covered_funcs), len(cl_not_covered_funcs) + len(cl_covered_funcs), cov_pctg_funcs)
        print(IND + "Covered '{}' smatch entries: {}/{} => {:.2f}% ({})".format(cl, len(covered_class), len(covered_class) + len(not_covered_class), cov_pctg, funcs_stats_str))
    total_cov_pctg = 100 * len(cov_non_excl)/(len(cov_non_excl) + len(not_cov_non_excl)) if len(cov_non_excl) > 0 else 0
    print(IND + "Total coverage (disregard 'unclassified', 'exclude', and 'wrapper' entries): {}/{} => {:.2f}%".format(len(cov_non_excl), (len(cov_non_excl) + len(not_cov_non_excl)), total_cov_pctg))

    # Exit if only printing summary stats
    if args.only_summary:
        return

    print("##############\n")
    print("SMATCH coverage")
    print("##############")
    print_lines = not args.only_funcs
    class_filter = args.class_filter
    function_filter = args.function_filter
    class_re = re.compile(class_filter) if len(class_filter) > 0 else None
    function_re = re.compile(function_filter) if len(function_filter) > 0 else None

    def func_name_key(e):
        return e[2]  # Sort by function name

    for k, v in groupby(sorted(smatch_set, key=func_name_key), func_name_key):
        if function_re and not function_re.match(k):
            continue
        cov_sign = SYMBOL_PARTIAL_COV if k in partially_covered_funcs else (SYMBOL_COV if k in covered_funcs else SYMBOL_NOT_COV
                                                                            )
        # Get filtered covered and non-covered items for function
        f_covered = list(filter(lambda e: e[2] == k and (len(class_filter) == 0 or class_re.match(e[0])) and not args.only_non_covered, covered))
        f_not_covered = list(filter(lambda e: e[2] == k and (len(class_filter) == 0 or class_re.match(e[0])), not_covered))

        # Skip functions with no entries (e.g., due to filter)
        if len(f_covered) == 0 and len(f_not_covered) == 0:
            continue

        print(f"{IND}{cov_sign} {k}()")
        for c, l, f in sorted(f_covered):
            if print_lines and not args.only_non_covered:
                print(f"{IND*2}{SYMBOL_COV} {c} {l}")
        for c, l, f in filter(lambda e: e[2] == k, f_not_covered):
            if print_lines:
                print(f"{IND*2}{SYMBOL_NOT_COV} {c} {l}")

    if args.reachability:
        print("##############\n")
        print("SMATCH reachability")
        print("##############")
        s = set()
        s_partial = set()

        s_safe = set()
        s_safe_partial = set()
        for c, l, f in filter(lambda e: e[0] == SMATCH_CAT_CONCERN, not_covered):
            if f in not_covered_funcs:
                s.add(f)
            else:
                s_partial.add(f)

        for c, l, f in filter(lambda e: e[0] == SMATCH_CAT_SAFE, not_covered):
            # Skip concern funcs
            if f in s or f in s_partial:
                continue
            if f in not_covered_funcs:
                s_safe.add(f)
            else:
                s_safe_partial.add(f)

        print(f"Not covered {SMATCH_CAT_SAFE} functions:")
        for e in s_safe:
            print(f"\t{e}")
        print(f"\nPartially covered {SMATCH_CAT_SAFE} functions:")
        for e in s_safe_partial:
            print(f"\t{e}")
        print()

        print(f"Not covered {SMATCH_CAT_CONCERN} functions:")
        for e in s:
            print(f"\t{e}")
        print(f"Partially covered {SMATCH_CAT_CONCERN} functions:")
        for e in s_partial:
            print(f"\t{e}")
        print()

        if smdb_available and args.reachability and os.path.isfile(args.smatch_reachability_db_file):
            print(IND + f"Did not reach the following functions reachable from '{KERNEL_ANALYSIS_START_FUNCS}':")
            print(IND + "(takes a while to generate...)")
            # Excludes 'exclude' and 'wrapper' entries
            reachable_non_covered = set()
            non_reachable_non_covered = set()
            for start_func in KERNEL_ANALYSIS_START_FUNCS:
                for e in not_cov_non_excl:
                    if smdb.is_reachable_from(start_func, e[2], max_depth=7):
                        if e[2] in not_covered_funcs:
                            reachable_non_covered.add(e)
                            try:
                                non_reachable_non_covered.remove(e)
                            except (KeyError, ValueError):
                                # ignore
                                pass
                    elif e not in reachable_non_covered:
                        non_reachable_non_covered.add(e)
            for f in set(map(lambda e: e[2], reachable_non_covered)):
                print(f"{IND}{IND}- {f}")
            for f in set(map(lambda e: e[2], non_reachable_non_covered)):
                print(f"{IND}{IND}? {f}")

            cov_tot = set(cov_non_excl)
            not_cov_tot = set(not_cov_non_excl) - non_reachable_non_covered
            tot_pctg = 100*len(cov_tot)/(len(cov_tot) + len(not_cov_tot)) if (len(cov_tot) + len(not_cov_tot)) > 0 else 0
            print(IND + "Total coverage (disregard unreachable, 'exclude' and 'wrapper' entries): {}/{} => {:.2f}%".format(len(cov_tot), (len(cov_tot) + len(not_cov_tot)), tot_pctg))


def main():
    parser = argparse.ArgumentParser(
        description='Smatch trace matching and analysis.\n'
        'Match line coverage file against smatch report.\n'
        '\tSymbols: [\'+\' -> covered, \'-\' -> not covered, \'/\' -> partially covered]')
    parser.add_argument('input_items', metavar='<input_item>', type=str, nargs='+',
                        help='Line coverage files or kAFL workdirs to match against smatch. \
            If a kAFL workdir, input_item should be a kAFL workdir with target  \
            in /target/ and traces in /traces/. If not used for kAFL, you need to set --smatch')
    parser.add_argument('-s', '--smatch', metavar='<smatch_file>', type=str,
                        help='use alternative smatch report file to match against')
    parser.add_argument('-S', '--only-summary', action="store_true",
                        help='only print abridged summary stats')
    parser.add_argument('-n', '--only-non-covered', action="store_true",
                        help='only print non-covered items')
    parser.add_argument('-f', '--only-funcs', action="store_true",
                        help='only print function coverage information')
    parser.add_argument('--class-filter', metavar='<class_filter>', type=str, default="",
                        help='only print entries where the classification matches this regex filter. E.g., --class-filter=\"concern|safe\"')
    parser.add_argument('--function-filter', metavar='<function_filter>', type=str, default="",
                        help='only print entries where the function name matches this regex filter. E.g., --function-filter=\"start_kernel\"')
    parser.add_argument('--combine-cov-files', action="store_true",
                        help=f'use the combined coverage of the files {LINECOV_FILES}')
    parser.add_argument('--ignore-errors', action="store_true",
                        help='do not exit on errors')
    parser.add_argument('--smatch-reachability-db-file', metavar='<db_file>', type=str, default=SMATCH_REACHABILITY_DB_FILE,
                        help=f'Global db file to use. Defaults to {GLOBAL_DB_FILE}')
    parser.add_argument('--db-file', metavar='<db_file>', type=str, default=GLOBAL_DB_FILE,
                        help=f'Global db file to use. Defaults to {GLOBAL_DB_FILE}')
    parser.add_argument('--save', action="store_true",
                        help='save coverage in global db')
    parser.add_argument('--load', action="store_true",
                        help='load earlier coverage from global db')
    parser.add_argument('--reachability', action="store_true",
                        help='do reachability analysis on results. Requires smatch_db.sqlite in your current dir (generated using smatch_scripts/build_kernel_data.sh)')

    args = parser.parse_args()

    if args.smatch and not os.path.isfile(args.smatch):
        print(f"Could not find smatch report {args.smatch}", file=sys.stderr)
        sys.exit()

    start(args)


if __name__ == "__main__":
    main()
