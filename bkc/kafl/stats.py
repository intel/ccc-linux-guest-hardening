#!/usr/bin/env python3
#
# Copyright (C) 2022 Intel Corporation

import os
import sys

import glob
import msgpack
import argparse
import subprocess

from pathlib import Path
from pprint import pprint

from time import strftime
from datetime import timedelta

import humanize


def msgpack_read(pathname):
    with open(pathname, 'rb') as f:
        return msgpack.unpackb(f.read(), strict_map_key=False)

def pprint_last_findings(stats):
    last = dict()
    stop_time = stats['start_time'] + stats['runtime']
    last_time = stats['aggregate']['last_found']
    for exit in ['regular', 'crash', 'kasan', 'timeout']:
        if last_time[exit] == 0:
            last[exit] = "N/A"
        else:
            last[exit] = timedelta(
                    seconds=int(stop_time-last_time[exit]))
    return last

def estimate_done(stats):
    num_favs  = stats['favs_total']
    num_norms = stats['findings']['regular'] - stats['favs_total']

    if stats['total_execs'] == 0 or num_favs + num_norms == 0:
        print(f"No execs or no paths in {stats['path']}. Skipping..", file=sys.stderr)
        return 0

    if num_favs > 0:
        done_favs = 100*stats['aggregate']['fav_states'].get('final', 0) / num_favs
    else:
        done_favs = 100
    if num_norms > 0:
        done_norms = 100*stats['aggregate']['norm_states'].get('final', 0) / num_norms
    else:
        done_norms = 100
    crash_fraction = (stats['paths_total']-stats['findings']['regular'])/stats['paths_total']*100
    done_total = 0.7*done_favs + 0.2*done_norms + 0.1*crash_fraction
    return done_total

def print_stats(args, stats):
    last_find = pprint_last_findings(stats)
    done_total = estimate_done(stats)

    workdir = f"{stats['name']}/{stats['path'].name}"
    runtime = humanize.naturaldelta(timedelta(seconds=stats['runtime']))

    print(f"{workdir}\n  Runtime: {runtime}, {done_total:2.0f}% done")
    for i in ['regular', 'crash', 'kasan', 'timeout']:
        print(f"  {i:>10}: {stats['findings'][i]:4d} (last: {last_find[i]})")

def print_html(args, stats, plotfile):
    last_find = pprint_last_findings(stats)
    done_total = estimate_done(stats)

    print("<table>\n<tr><th align=left>%s</th></tr>" % stats['name'])
    print("<tr><td><pre>")
    print("Total runtime:    " + humanize.naturaldelta(timedelta(seconds=stats['runtime'])))
    print("Total executions: " + humanize.intword(stats['total_execs']))
    print("Edges in bitmap:  " + humanize.intcomma(stats['bytes_in_bitmap']))
    print("Estimated done:    ~%d%%" % done_total)

    if done_total > 0:
        print("\nPerformance")
        print("  Avg. exec/s:  " + humanize.intcomma(stats['execs']))
        print("  Timeout rate: %3.2f%%" % (stats['num_timeout']/stats['total_execs']*100))
        print("  Funky rate:   %3.2f%%" % (stats['num_funky']/stats['total_execs']*100))
        print("  Reload rate:  %3.2f%%" % (stats['num_reload']/stats['total_execs']*100))
        print("\nCorpus (%s paths)" % humanize.intcomma(stats['paths_total']))
        print("  regular:   %4d (last: %s)" % (stats['findings']['regular'], last_find['regular']))
        print("  crashes:   %4d (last: %s)" % (stats['findings']['crash'], last_find['crash']))
        print("  sanitizer: %4d (last: %s)" % (stats['findings']['kasan'], last_find['kasan']))
        print("  timeout:   %4d (last: %s)" % (stats['findings']['timeout'], last_find['timeout']))

        queue_stages = {
                'initial': 'init',
                'redq/grim': 'rq/gr',
                'deterministic': 'deter',
                'havoc': 'havoc',
                'final': 'final' }

        print("\nQueue Progress")
        print("  %5s  %4s    %4s" % ("Stage", "Favs", "Norm"))
        for stage in queue_stages:
            print("  %5s: %4d  / %4d" % (queue_stages[stage],
                                      stats['aggregate']['fav_states'].get(stage, 0),
                                      stats['aggregate']['norm_states'].get(stage, 0)))

        print("\nMutation Yields")
        for method, num in stats['aggregate']['yield'].items():
            print("  %12s: %4d" % (method, num))

    print("</pre></td><td>")
    if plotfile.is_file():
        print(f"<img width=700 src=\"{plotfile.relative_to(args.searchdir)}\">")

    print("</td></tr>")

    #print("<tr><td><details><summary>kAFL config</summary><pre>")
    #pprint(msgpack_read(workdir/"config"))
    #print("</pre></details></td></tr>")
    print("</table>\n")

def stats_aggregate(stats):

    ret = {
            "fav_states": {},
            "norm_states": {},
            "last_found": {"regular": 0, "crash": 0, "kasan": 0, "timeout": 0},
            "yield": {},
            }

    methods = {
            'import': "seed/import",
            'kickstart': "kickstart",
            'calibrate': "calibrate",
            'trim': "trim",
            'trim_center': "trim_center",
            'stream_color': "stream_color",
            'stream_zero': "stream_zero",
            'redq_color': "redq_color",
            'redq_mutate': "redq_mutate",
            'redq_dict': "redq_dict",
            'grim_infer': "grim_infer",
            'grim_havoc': "grim_havoc",
            'afl_arith_1': "afl_arith",
            'afl_arith_2': "afl_arith",
            'afl_arith_4': "afl_arith",
            'afl_flip_1/1': "afl_flip",
            'afl_flip_2/1': "afl_flip",
            'afl_flip_8/1': "afl_flip",
            'afl_flip_8/2': "afl_flip",
            'afl_flip_8/4': "afl_flip",
            'afl_int_1': "afl_int",
            'afl_int_2': "afl_int",
            'afl_int_4': "afl_int",
            'afl_havoc': "afl_havoc",
            'afl_splice': "afl_splice",
            'radamsa': "radamsa",
            'trim_funky': "funky",
            'stream_funky': "funky",
            'validate_bits': "funky",
            'fixme': "funky",
            'redq_trace': "funky",
            }

    for node in stats['nodes'].values():
        reason = node['info']['exit_reason']
        last_found = ret['last_found'][reason]
        ret['last_found'][reason] = max(last_found, node['info']['time'])

        if reason == "regular":
            state = node['state']['name']
            if len(node['fav_bits']) >0:
                fav = "fav_states"
            else:
                fav = "norm_states"

            ret[fav][state] = ret[fav].get(state, 0) + 1

    for method, num in stats['yield'].items():
        name=methods[method]
        ret['yield'][methods[method]] = num

    stats['aggregate'] = ret

def generate_plots(workdir):
    GNUPLOT_SCRIPT=Path(os.environ.get("BKC_ROOT"))/"bkc"/"kafl"/"stats.plot"
    STATS_INPUT=workdir/"stats.csv"
    STATS_OUTPUT=workdir/"stats.png"

    if not STATS_OUTPUT.is_file():
        cmd = [ "gnuplot",
                "-e", f'set terminal png size 900,800 enhanced; set output "{STATS_OUTPUT}"',
                "-c", f"{GNUPLOT_SCRIPT}",
                f"{STATS_INPUT}"]

        p = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
        if p.returncode != 0:
            print(f"Failed to execute: {cmd}. Output:", file=sys.stderr)
            print(p.stderr, file=sys.stderr)

    return STATS_OUTPUT

def process_workdir(workdir):
    workers = dict()
    nodes = dict()

    stats_path = workdir/"stats"
    stats_path = workdir/"stats"
    if stats_path.is_file():
        #pprint(stats)
        stats = msgpack_read(stats_path)

    for num in range(stats['num_workers']):
        workers_path = workdir/f"worker_stats_{num}"
        if workers_path.is_file():
            workers[num] = msgpack_read(workers_path)

    num_nodes = sum([num for num in stats['findings'].values()])
    for nid in range(num_nodes):
        nodes_path = workdir/"metadata/node_{:05d}".format(nid)
        if nodes_path.is_file():
            nodes[nid] = msgpack_read(nodes_path)

    stats['name'] = workdir.parent.name
    stats['path'] = workdir
    stats['runtime'] = max([worker['run_time'] for worker in workers.values()])
    stats['workers'] = workers
    stats['nodes'] = nodes
    stats['execs'] = int(stats['total_execs']/stats['runtime'])
    stats['paths_total'] = num_nodes

    return stats

def main():

    parser = argparse.ArgumentParser(description="kAFL Workdir Summary")
    parser.add_argument("searchdir", help="folder to scan for kAFL workdirs")
    parser.add_argument("--html", action="store_true", help="produce more detailed html output")
    args = parser.parse_args()

    candidates = Path(args.searchdir).rglob("stats.csv")

    for c in sorted(candidates):
        stats = process_workdir(c.parent)
        stats_aggregate(stats)
        if args.html:
            plotfile = generate_plots(c.parent)
            print_html(args, stats, plotfile)
        else:
            print_stats(args,stats)


if __name__ == "__main__":
    main()
