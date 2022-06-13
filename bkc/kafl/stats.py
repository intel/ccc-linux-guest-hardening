#!/usr/bin/env python3
#
# Copyright (C) 2022 Intel Corporation

import os
import sys

import glob
import msgpack
import argparse
from pathlib import Path
from pprint import pprint

from time import strftime
from datetime import timedelta

import humanize


def msgpack_read(pathname):
    with open(pathname, 'rb') as f:
        return msgpack.unpackb(f.read(), strict_map_key=False)

def stats_print(stats):

    last = dict()
    days_limit = 60*60*24*2
    runtime = stats['runtime']
    stop_time = stats['start_time'] + runtime
    last_time = stats['aggregate']['last_found']
    favs_done = stats['favs_total']-stats['favs_pending']

    for exit in ['regular', 'crash', 'kasan', 'timeout']:
        if last_time[exit] == 0:
            last[exit] = "N/A"
        else:
            last[exit] = timedelta(
                    seconds=int(stop_time-last_time[exit]))
    
    print(f"<tr><th align=left>{stats['name']}</th></tr>")
    print("<tr><td><pre>")
    print("  Runtime: " + humanize.naturaldelta(timedelta(seconds=runtime)))
    print("    Execs: " + humanize.intword(stats['total_execs']))
    print("    Avg:   " + humanize.intcomma(stats['execs']))
    print("")
    print(f"  Paths: " + humanize.intcomma(stats['paths_total']))
    print(f"    regular:   {stats['findings']['regular']}\t(last: {last['regular']})")
    print(f"    crashes:   {stats['findings']['crash']}  \t(last: {last['crash']})")
    print(f"    sanitizer: {stats['findings']['kasan']}  \t(last: {last['kasan']})")
    print(f"    timeout:   {stats['findings']['timeout']}\t(last: {last['timeout']})")
    print("")
    print(f"  Queue Status")

    queue_stages = {
            'initial': 'init',
            'redq/grim': 'rq/gr',
            'deterministic': 'deter',
            'havoc': 'havoc',
            'final': 'final' }

    print("    %5s  %4s    %4s" % ("Stage", "Favs", "Norm"))
    for stage in queue_stages:
        print("    %5s: %4d  / %4d" % (queue_stages[stage],
                                  stats['aggregate']['fav_states'].get(stage, 0),
                                  stats['aggregate']['norm_states'].get(stage, 0)))

    num_favs  = stats['favs_total']
    num_norms = stats['findings']['regular'] - stats['favs_total']
    done_favs  = 100*stats['aggregate']['fav_states'].get('final', 0) / num_favs
    done_norms = 100*stats['aggregate']['norm_states'].get('final', 0) / num_norms

    print("     %s: %3d%%  / %3d%%" % ("Done", done_favs, done_norms))
    print("</pre></td><td>")
    print(f"<img width=500 src=\"./{stats['name']}/stats.png\">")
    print("</td></tr>")

def stats_aggregate(stats):

    ret = {
            "fav_states": {},
            "norm_states": {},
            "last_found": {"regular": 0, "crash": 0, "kasan": 0, "timeout": 0},
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

    stats['aggregate'] = ret

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

    stats['name'] = workdir.name
    stats['runtime'] = max([worker['run_time'] for worker in workers.values()])
    stats['workers'] = workers
    stats['nodes'] = nodes
    stats['execs'] = int(stats['total_execs']/stats['runtime'])
    stats['paths_total'] = num_nodes

    return stats

def main():

    parser = argparse.ArgumentParser(description="kAFL Workdir Summary")
    parser.add_argument("searchdir", help="folder to scan for kAFL workdirs")
    args = parser.parse_args()

    candidates = Path(args.searchdir).rglob("stats.csv")

    for c in sorted(candidates):
        stats = process_workdir(c.parent)
        stats_aggregate(stats)
        print("<table>")
        stats_print(stats)
        print("</table>")


if __name__ == "__main__":
    main()
