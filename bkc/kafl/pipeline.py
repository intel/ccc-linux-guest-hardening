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
from pathlib import Path

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

BKC_ROOT = Path(os.environ.get('BKC_ROOT'))
RUNNER = BKC_ROOT/'bkc/kafl/fuzz.sh'
DEFAULT_GUEST_CONFIG = BKC_ROOT/'bkc/kafl/linux_kernel_tdx_guest.config'
USE_GHIDRA=0 # use ghidra for gen_addr2line.sh?
DRY_RUN_FUZZ="--abort-exec 100"

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

    if all_exist(touchfiles):
        return

    subprocess.run(
            f"MAKEFLAGS='-j{NUM_THREADS}' {RUNNER} audit {audir_dir} {config}",
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

    if all_exist([target_dir/f.name for f in target_files]):
        return

    subprocess.run(
            f"MAKEFLAGS='-j{NUM_THREADS}' {RUNNER} build {harness_dir} {build_dir}",
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
            f"KAFL_WORKDIR={work_dir} {RUNNER} run {target_dir} {DRY_RUN_FUZZ} -p {NUM_WORKERS}",
            shell=True, check=True, cwd=harness_dir)

@python_app
def task_trace(args, harness_dir, work_dir):

    import os
    import subprocess

    subprocess.run(
            f"{RUNNER} cov {work_dir} -p {NUM_THREADS}",
            shell=True, check=True, cwd=harness_dir)

@python_app
def task_smatch(args, work_dir, smatch_list):

    import os
    import subprocess
    import shutil

    subprocess.run(
            f"USE_GHIDRA={USE_GHIDRA} MAKEFLAGS='-j{NUM_THREADS}' {RUNNER} smatch {work_dir}",
            shell=True, check=True)

def run_campaign(args, harness_dirs):
    # smatch audit
    audit_dir = CAMPAIGN_ROOT/'audit_list'
    os.makedirs(audit_dir, exist_ok=True)
    global_smatch_warns = audit_dir/'smatch_warns.txt'
    global_smatch_list = audit_dir/'smatch_warns_annotated.txt'

    # audit based on TDX fuzzing template
    # this is required to run inside the kernel source tree
    config = DEFAULT_GUEST_CONFIG
    t = task_audit(args, audit_dir, config, touchfiles=[global_smatch_warns, global_smatch_list])
    t.result() # wait to complete

    pipeline = dict()
    for harness in harness_dirs:
        pipeline.update({harness.name: {
            'harness_dir': harness,
            'target_dir': harness/'target',
            'build_dir': mkjobdir(harness, 'build'),
            'work_dir': mkjobdir(harness, 'run')
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

    parser = argparse.ArgumentParser(description='Campaign Automation')
    parser.add_argument('campaign', metavar='<campaign>', type=str, nargs="+",
            help='root campaign dir or one or more harness dirs (files may be overwritten!))')
    parser.add_argument('--pattern', metavar='<pattern>', type=str,
            help='filter pattern for which harnesses to schedule')
    parser.add_argument('--keep', '-k', action="store_true", help="keep build files")
    parser.add_argument('--verbose', '-v', action="store_true", help="verbose mode")
    parser.add_argument('--dry-run', '-n', action="store_true", help="abort fuzzing after 100 execs")

    return parser.parse_args()

def main():

    global NCPU
    global NUM_WORKERS
    global NUM_THREADS
    global CAMPAIGN_ROOT
    global DRY_RUN_FUZZ

    args = parse_args()

    harness_dirs = list()
    for c in args.campaign:
        for harness in Path(c).glob('**/kafl.yaml'):
            if args.pattern and args.pattern not in harness.parent.name:
                continue
            print(f"Selected harness: {harness.parent}")
            harness_dirs.append(harness.parent)

    # pick root based on first harness' parent
    CAMPAIGN_ROOT = Path(harness_dirs[0].parent)

    # Scale workers/threads based on available CPUs
    NCPU=len(os.sched_getaffinity(0)) # available vCPUs
    NUM_WORKERS=16 # kAFL workers (max 1 per vCPU)
    NUM_THREADS=32 # SW threads to schedule (can to overcommit)

    # use few threads/pipes for small CPU
    if NCPU < NUM_WORKERS:
        NUM_PIPES=1
        NUM_WORKERS=NCPU
        NUM_THREADS=2*NCPU
    else:
        NUM_PIPES=max(1,(NCPU-2)//NUM_WORKERS) # concurrent pipelines

    # use more threads when relatively few pipes
    if NUM_PIPES > len(harness_dirs):
        NUM_PIPES = len(harness_dirs)
        NUM_THREADS = 2*NCPU//NUM_PIPES
        #NUM_WORKERS = NCPU//NUM_PIPES

    print(f"Executing %d harnesses in %d pipelines (%d workers, %d threads across %d CPUs)" % (
        len(harness_dirs), NUM_PIPES, NUM_WORKERS, NUM_THREADS, NCPU))

    # define pipeline number based on python threads
    local_threads = Config(
        executors=[
            ThreadPoolExecutor(
                max_threads=NUM_PIPES,
                label='local_threads'
            )
        ]
    )
    parsl.load(local_threads)

    if args.verbose:
        parsl.set_stream_logger(level=parsl.logging.INFO)
        #parsl.set_file_logger(FILENAME, level=logging.DEBUG)

    if not args.dry_run:
        DRY_RUN_FUZZ = ''

    run_campaign(args, harness_dirs)

if __name__ == "__main__":
    main()
