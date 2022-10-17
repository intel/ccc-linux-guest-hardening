#!/usr/bin/env python3
#
# Fuzzing campaign pipeline
#
# Schedules `fuzz.sh` jobs based on available CPU
#
# Usage / Notes
#
# - Currently assumes ansible install + make prepare has been run
#   (--asset-root can be used to point to the outputs of make prepare)
#
# - Use with non-existing campaign root to generate desired harness configs
#   (--harness <pattern> is again interpreted as filter to desired harnesses)
#
# - Use with existing campaign root to discover + run harnesses there
#
#   - Provide multiple target folders and/or constrain selection with --harness <pattern>
#     --rebuild forces a kernel rebuild even if target/ components already exist for the harness
#
# - Currently not clever enough to properly delete partial result on failure/abort,
#   which also means we cannot reasonably scan + resume an aborted run
#
# - But you can always inspect the target folders and run the subtask manually there: most pipeline tasks
#   are simply executing `fuzz.sh` from the harness folder and pickup the relevant configs/files from there

import os
import sys

import glob
import tempfile
import argparse
import shutil
import time
import subprocess


from pathlib import Path
from pprint import pformat

import parsl
from parsl.app.app import python_app, bash_app
from parsl.data_provider.files import File

from parsl.config import Config
from parsl.executors.threads import ThreadPoolExecutor

#
# Helpers
#

def check_inputs(inputs):
    for f in inputs:
        if not os.path.exists(f):
            raise parsl.app.errors.ParslError(f"Missing input file {f}")

def mkjobdir(job_root, label):
    os.makedirs(job_root, exist_ok=True)
    tmpdir = tempfile.mkdtemp(dir=job_root, prefix=f"{label}_")
    os.chmod(tmpdir, 0o755)
    return Path(tmpdir)

def all_exist(touchfiles):
    for f in touchfiles:
        if not os.path.exists(f):
            return False
    return True

#
# Task wrappers
#

@python_app
def task_build(args, harness_dir, build_dir, target_dir,
               global_smatch_warns, global_smatch_list):

    import os
    import subprocess
    import shutil

    target_files = [
            build_dir/'.config',
            build_dir/'vmlinux',
            build_dir/'System.map',
            build_dir/'arch/x86/boot/bzImage',
            global_smatch_warns,
            global_smatch_list ]

    os.makedirs(target_dir, exist_ok=True)

    if not args.rebuild:
        if all_exist([target_dir/f.name for f in target_files]):
            shutil.rmtree(build_dir)
            return

    env = dict(os.environ, MAKEFLAGS=f"-j{args.threads}")
    logfile = build_dir/'task_build.log'

    print(f"Starting build job at {build_dir} (log: {logfile.name})")
    with open(logfile, 'w') as log:
        p = subprocess.run([args.fuzz_sh, "build", harness_dir, build_dir],
                shell=False, check=True, env=env,
                stdout=log, stderr=subprocess.STDOUT)

    if p.returncode != 0:
        return

    for f in target_files:
        shutil.copy(f, target_dir)
        shutil.copy(logfile, target_dir)
    if not args.keep:
        shutil.rmtree(build_dir)

@python_app
def task_fuzz(args, harness_dir, target_dir, work_dir):

    import os
    import subprocess

    if ((work_dir/'stats').exists() and
        (work_dir/'worker_stats_0').exists()):
        print(f"Skip fuzzing for existing workdir {work_dir}..")
        return

    env = dict(os.environ, KAFL_WORKDIR=f"{work_dir}")
    logfile = work_dir/'task_fuzz.log'

    print(f"Starting fuzzer job at {work_dir} (log: {logfile.name})")
    with open(logfile, 'w') as log:
        subprocess.run([args.fuzz_sh, "run", target_dir, *args.kafl_extra, "-p", str(args.workers)],
                shell=False, check=True, env=env, cwd=harness_dir,
                stdout=log, stderr=subprocess.STDOUT)

@python_app
def task_trace(args, harness_dir, work_dir):

    import os
    import subprocess

    logfile = work_dir/'task_trace.log'

    print(f"Starting trace job at {work_dir} (log: {logfile.name})")
    with open(logfile, 'w') as log:
        subprocess.run([args.fuzz_sh, "cov", work_dir, "-p", str(args.workers)],
                shell=False, check=True, cwd=harness_dir,
                stdout=log, stderr=subprocess.STDOUT)

@python_app
def task_smatch(args, work_dir, smatch_list, wait_task=None):

    import os
    import subprocess

    # wait on dependency... :-/
    if wait_task:
        wait_task.result()

    env = dict(
            os.environ,
            MAKEFLAGS=f"-j{args.threads}",
            USE_GHIDRA=str(int(args.use_ghidra)),
            USE_FAST_MATCHER=str(int(args.use_fast_matcher)))
    logfile = work_dir/'task_smatch.log'

    print(f"Starting smatch job at {work_dir} (log: {logfile.name})")
    with open(logfile, 'w') as log:
        subprocess.run([args.fuzz_sh, "smatch", work_dir],
                shell=False, check=True, env=env,
                stdout=log, stderr=subprocess.STDOUT)


@python_app
def task_triage(args):

    import os
    import subprocess

    # generate stats output
    if args.stats_helper.exists():
        with open(args.campaign_root/'stats.log', 'w') as stats_log:
            subprocess.run([args.stats_helper, '--html', args.campaign_root/'stats.html', args.campaign_root],
                    shell=False, check=True, stdout=stats_log, stderr=subprocess.STDOUT)

    # sort / decode / summarize crash reports
    if args.triage_helper.exists():
        with open(args.campaign_root/'summary.log', 'w') as logfile:
            subprocess.run([args.triage_helper, args.campaign_root],
                    shell=False, check=True, cwd=args.campaign_root,
                    stdout=logfile, stderr=subprocess.STDOUT)


def run_campaign(args, harness_dirs):
    global_smatch_warns = args.asset_root/'smatch_warns.txt'
    global_smatch_list = args.asset_root/'smatch_warns_annotated.txt'


    pipeline = list()
    for harness in harness_dirs:
        workdirs = list(harness.glob('workdir_*'))
        if not workdirs or args.refuzz:
            workdirs = [mkjobdir(harness, 'workdir')]

        for workdir in workdirs:
            pipeline.append({
                'harness_name': harness.name,
                'harness_dir': harness,
                'target_dir': harness/'target',
                'build_dir': mkjobdir(harness, 'build'),
                'work_dir': workdir
                })

    build_tasks = []
    for p in pipeline:
        t = task_build(
                args,
                p['harness_dir'],
                p['build_dir'],
                p['target_dir'],
                global_smatch_warns, global_smatch_list)
        build_tasks.append(t)

    # wait for all build tasks to complete
    [t.result() for t in build_tasks]

    fuzz_tasks = []
    for p in pipeline:
        t = task_fuzz(
                args,
                p['harness_dir'],
                p['target_dir'],
                p['work_dir'])
        fuzz_tasks.append(t)

    # wait for all fuzz tasks to complete
    [t.result() for t in fuzz_tasks]

    trace_tasks = []
    for p in pipeline:
        t = task_trace(args, p['harness_dir'], p['work_dir'])
        #t.result()
        trace_tasks.append(t)
        t = task_smatch(args, p['work_dir'], global_smatch_list, wait_task=t)
        #t.result()
        trace_tasks.append(t)

    t = task_triage(args)
    trace_tasks.append(t)

    # wait for all tasks before exit
    [t.result() for t in trace_tasks]



def init_campaign(args, campaign_dir):

    if args.harness:
        pattern = args.harness
    else:
        pattern = "all"

    # generate harness configs
    subprocess.run([args.init_helper, campaign_dir, pattern, '--config', args.linux_conf],
            shell=False, check=True)
    print("")

def check_fast_matcher_built():
    bkc_root = Path(os.environ.get('BKC_ROOT'))
    fast_matcher_bin = bkc_root/'bkc/coverage/fast_matcher/target/release/fast_matcher'
    if not os.path.exists(fast_matcher_bin):
        sys.exit(f"Cannot find fast_matcher binary '{fast_matcher_bin}'. Please build first. Exiting.")

def dir_arg_type(d):
    p = Path(d)
    return p.resolve()

def parse_args():
    default_ncpu = len(os.sched_getaffinity(0))
    bkc_root = Path(os.environ.get('BKC_ROOT'))
    default_fuzzsh = bkc_root/'bkc/kafl/fuzz.sh'
    default_init  = bkc_root/'bkc/kafl/init_harness.py'
    default_config = bkc_root/'bkc/kafl/linux_kernel_tdx_guest.config'
    default_triage = bkc_root/'bkc/kafl/summarize.sh'
    default_stats = bkc_root/'bkc/kafl/stats.py'

    parser = argparse.ArgumentParser(description='Campaign Automation')
    parser.add_argument('campaign', metavar='<campaign>', type=dir_arg_type, nargs="+",
            help='root campaign dir or one or more harness dirs (files may be overwritten!))')
    parser.add_argument('--harness', metavar='<str>', type=str,
            help='only schedule harnesses containing this string (e.g. "BPH")'),

    parser.add_argument('--ncpu', '-j', type=int, metavar='n', default=default_ncpu,
            help=f'number of vCPUs to use (default: {default_ncpu})')
    parser.add_argument('--workers', '-p', type=int, metavar='n', default=16,
            help='number of kAFL workers (default: min(16,ncpu))')
    parser.add_argument('--threads', '-t', type=int, metavar='n', default=32,
            help='number of SW threads (default: 2*workers)')

    parser.add_argument('--rebuild', action="store_true",
            help="rebuild fuzz kernels")
    parser.add_argument('--refuzz', action="store_true",
            help="ignore existing workdirs in the campaign root (default: resume the pipeline)")
    parser.add_argument('--dry-run', '-n', action="store_true",
            help="abort fuzzer after 500 execs")
    parser.add_argument('--keep', action="store_true",
            help="keep kernel build trees")
    parser.add_argument('--verbose', '-v', action="store_true", help="verbose mode")

    parser.add_argument('--asset-root', metavar='<dir>', default=bkc_root,
            help=f"pre-compute / assets directory (default: {bkc_root})")
    parser.add_argument('--use-ghidra', metavar='<0|1>', type=bool, default=False,
            help="use Ghidra for deriving covered blocks from edges? (default=0)")
    parser.add_argument('--use-fast-matcher', metavar='<0|1>', type=bool, default=False,
            help="use fast_matcher for coverage mapping? (default=0)")

    parser.add_argument('--linux-conf', metavar='<file>', default=default_config,
            help=f"base config for kernel harness (default: {default_config})")
    parser.add_argument('--fuzz-sh', metavar='<file>', default=default_fuzzsh,
            help=f"fuzz.sh runner script (default: {default_fuzzsh})")
    parser.add_argument('--init-helper', metavar='<file>', default=default_init,
            help=f"init_harness.py helper script (default: {default_init})")
    parser.add_argument('--triage-helper', metavar='<file>', default=default_triage,
            help=f"triage helper script (default: {default_triage})")
    parser.add_argument('--stats-helper', metavar='<file>', default=default_stats,
            help=f"statistics helper script (default: {default_stats})")

    return parser.parse_args()


def main():

    args = parse_args()

    if args.use_fast_matcher:
        check_fast_matcher_built()

    # if campaign directory does not exist, create based on args
    if len(args.campaign) == 1 and not os.path.exists(args.campaign[0]):
        init_campaign(args, args.campaign[0])

    harness_dirs = list()
    for c in args.campaign:
        for harness in Path(c).glob('**/kafl.yaml'):
            if args.harness and args.harness not in harness.parent.name:
                continue
            harness_dirs.append(harness.parent)

    if len(harness_dirs) < 1:
        sys.exit(f"No matching harnesses found in campaign root. Abort.")

    # pick root based on first harness' parent
    args.campaign_root = Path(harness_dirs[0].parent)

    print(f"Setting campaign root to {args.campaign_root}")
    print(f"Scheduled for execution:\n%s" % pformat([str(h) for h in harness_dirs]))


    # for few CPUs, use single pipes and all available cores
    if args.ncpu < args.workers:
        args.pipes = 1
        args.workers = args.ncpu
        args.threads = 2*args.ncpu
    else:
        args.pipes = max(1,(args.ncpu-2)//args.workers)
        args.threads = 2*args.workers

    # if we don't need so many pipes, scale up the threads (but not workers)
    if args.pipes > len(harness_dirs):
        args.pipes = len(harness_dirs)
        args.threads = 2*(args.ncpu//args.pipes)

    # pipeline concurrency is done via parallel parsl jobs
    local_threads = Config(
        executors=[
            ThreadPoolExecutor(
                max_threads=args.pipes,
                label='local_threads'
            )
        ]
    )
    parsl.load(local_threads)

    args.kafl_extra = []
    if args.dry_run:
        args.kafl_extra = ["--abort-exec", "500"]

    print(f"\nExecuting %d harnesses in %d pipelines (%d workers, %d threads, %d cpus).\n" % (
        len(harness_dirs), args.pipes, args.workers, args.threads, args.ncpu))

    for i in "321":
        print(f"{i},", end='', flush=True)
        time.sleep(1)
    print(" Go!\n")

    run_campaign(args, harness_dirs)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExit on ctrl-c.\n")
        sys.exit(1)
