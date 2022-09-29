#!/usr/bin/env python3

#
# Fuzzing campaign pipeline
#
# Schedules `fuzz.sh` jobs based on available CPU
#

import os
import sys

import glob
import tempfile
import argparse
import shutil
import time

from pathlib import Path
from pprint import pformat

import parsl
from parsl.app.app import python_app, bash_app
from parsl.data_provider.files import File

from parsl.config import Config
from parsl.executors.threads import ThreadPoolExecutor

#
# Configuration
#

#from parsl.executors import WorkQueueExecutor
#worker_config = Config(
#        executors=[
#            WorkQueueExecutor(
#                # ...other options go here
#                autolabel=True,
#                autocategory=True
#                )
#            ]
#        )
#parsl.load(worker_config)

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

##
# Task wrappers
##

@python_app
def task_audit(args, audit_dir, config, touchfiles=[]):

    import os
    import subprocess

    if not args.rebuild and all_exist(touchfiles):
        return

    subprocess.run(
            f"MAKEFLAGS='-j{args.threads}' {args.fuzz_sh} audit {audit_dir} {config}",
            shell=True, check=True)

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
            return

    subprocess.run(
            f"MAKEFLAGS='-j{args.threads}' {args.fuzz_sh} build {harness_dir} {build_dir}",
            shell=True, check=True)

    for f in target_files:
        shutil.copy(f, target_dir)
    if not args.keep:
        shutil.rmtree(build_dir)

@python_app
def task_fuzz(args, harness_dir, target_dir, work_dir):

    import os
    import subprocess

    subprocess.run(
            f"KAFL_WORKDIR={work_dir} {args.fuzz_sh} run {target_dir} {args.dry_run} -p {args.workers}",
            shell=True, check=True, cwd=harness_dir)

@python_app
def task_trace(args, harness_dir, work_dir):

    import os
    import subprocess

    subprocess.run(
            f"{args.fuzz_sh} cov {work_dir} -p {args.workers}",
            shell=True, check=True, cwd=harness_dir)

@python_app
def task_smatch(args, work_dir, smatch_list):

    import os
    import subprocess
    import shutil

    if args.use_ghidra:
        USE_GHIDRA=1
    else:
        USE_GHIDRA=0

    subprocess.run(
            f"USE_GHIDRA={USE_GHIDRA} MAKEFLAGS='-j{args.threads}' {args.fuzz_sh} smatch {work_dir}",
            shell=True, check=True)

def run_campaign(args, harness_dirs):
    # smatch audit
    audit_dir = args.campaign_root/'audit_list'
    os.makedirs(audit_dir, exist_ok=True)
    global_smatch_warns = audit_dir/'smatch_warns.txt'
    global_smatch_list = audit_dir/'smatch_warns_annotated.txt'

    # audit based on TDX fuzzing template
    # this is required to run inside the kernel source tree
    config = args.linux_conf
    t = task_audit(args, audit_dir, config, touchfiles=[global_smatch_warns, global_smatch_list])
    t.result() # wait to complete

    pipeline = dict()
    for harness in harness_dirs:
        pipeline.update({harness.name: {
            'harness_dir': harness,
            'target_dir': harness/'target',
            'build_dir': mkjobdir(harness, 'build'),
            'work_dir': mkjobdir(harness, 'workdir')
            }})

    for p in pipeline.values():
        t = task_build(
                args,
                p['harness_dir'],
                p['build_dir'],
                p['target_dir'],
                global_smatch_warns, global_smatch_list)

        t.result() # wait for build to be done

    fuzz_tasks = []
    for p in pipeline.values():
        t = task_fuzz(
                args,
                p['harness_dir'],
                p['target_dir'],
                p['work_dir'])
        fuzz_tasks.append(t)

    # wait for all build jobs to complete
    [t.result() for t in fuzz_tasks]

    for p in pipeline.values():
        t = task_trace(args, p['harness_dir'], p['work_dir'])
        t.result()
        t = task_smatch(args, p['work_dir'], global_smatch_list)
        t.result()

def parse_args():
    bkc_root = Path(os.environ.get('BKC_ROOT'))
    default_ncpu = len(os.sched_getaffinity(0))
    default_fuzzsh = bkc_root/'bkc/kafl/fuzz.sh'
    default_config = bkc_root/'bkc/kafl/linux_kernel_tdx_guest.config'

    parser = argparse.ArgumentParser(description='Campaign Automation')
    parser.add_argument('campaign', metavar='<campaign>', type=str, nargs="+",
            help='root campaign dir or one or more harness dirs (files may be overwritten!))')
    parser.add_argument('--harness', metavar='<str>', type=str,
            help='only schedule harnesses containing this string (e.g. "BPH")'),

    parser.add_argument('--ncpu', '-j', type=int, metavar='n', default=default_ncpu,
            help=f'number of vCPUs to use (default: {default_ncpu})')
    parser.add_argument('--workers', '-p', type=int, metavar='n', default=16,
            help='number of kAFL workers (default: min(16,ncpu))')
    parser.add_argument('--threads', '-t', type=int, metavar='n', default=32,
            help='number of SW threads (default: 2*workers)')

    parser.add_argument('--rebuild', '-r', action="store_true",
            help="rebuild audit and fuzz kernels")
    parser.add_argument('--keep', '-k', action="store_true",
            help="keep kernel build trees")
    parser.add_argument('--dry-run', '-n', action="store_true",
            help="kill fuzzer after 100 execs (corpus may be empty)")
    parser.add_argument('--verbose', '-v', action="store_true", help="verbose mode")

    parser.add_argument('--linux-conf', metavar='<file>', default=default_config,
            help=f"base config for generating audit and harness kernels (default: {default_config})")
    parser.add_argument('--fuzz-sh', metavar='<file>', default=default_fuzzsh,
            help=f"fuzz.sh runner script (default: {default_fuzzsh})")
    parser.add_argument('--use-ghidra', metavar='<0|1>', type=bool, default=False,
            help="use Ghidra for deriving covered blocks from edges? (default=0)")

    return parser.parse_args()

def main():

    args = parse_args()

    harness_dirs = list()
    for c in args.campaign:
        for harness in Path(c).glob('**/kafl.yaml'):
            if args.harness and args.harness not in harness.parent.name:
                continue
            harness_dirs.append(harness.parent)

    print(f"Selected harnesses:\n%s" % pformat([str(h) for h in harness_dirs]))

    # pick root based on first harness' parent
    args.campaign_root = Path(harness_dirs[0].parent)

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

    if args.verbose:
        parsl.set_stream_logger(level=parsl.logging.INFO)
        #parsl.set_file_logger(FILENAME, level=logging.DEBUG)

    if args.dry_run:
        args.dry_run = "--abort-exec 100"
    else:
        args.dry_run = ""

    print(f"\nExecuting %d harnesses in %d pipelines (%d workers, %d threads, %d cpus)." % (
        len(harness_dirs), args.pipes, args.workers, args.threads, args.ncpu))

    for i in "4321\n":
        time.sleep(1)
        print(f"{i},", end='', flush=True)

    run_campaign(args, harness_dirs)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExit on ctrl-c.\n")
