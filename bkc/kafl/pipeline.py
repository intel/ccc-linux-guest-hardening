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

def pfile(path: Path) -> File:
    return File(path.as_uri())

##
# Task wrappers
##

@bash_app
def mrproper(inputs=[], outputs=[], stderr=parsl.AUTO_LOGNAME, stdout=parsl.AUTO_LOGNAME):
    print(f"mrproper: {inputs[0]}")
    check_inputs(inputs)
    return f"cd {inputs[0]}; MAKEFLAGS='-j{NUM_THREADS}' make mrproper"

@bash_app
def build(inputs=[], outputs=[], stderr=parsl.AUTO_LOGNAME, stdout=parsl.AUTO_LOGNAME):
    print(f"build: {inputs[0]}")
    check_inputs(inputs)
    return f"MAKEFLAGS='-j{NUM_THREADS}' {RUNNER} build {inputs[0]} {outputs[0]}"

@bash_app
def fuzz(inputs=[], outputs=[], stderr=parsl.AUTO_LOGNAME, stdout=parsl.AUTO_LOGNAME):
    print(f"fuzz: {inputs[0]}")
    check_inputs(inputs)
    return f"KAFL_WORKDIR={outputs[0]} {RUNNER} run {inputs[0]} {DRY_RUN_FUZZ} -p {NUM_WORKERS}"

@bash_app
def trace(inputs=[], outputs=[], stderr=parsl.AUTO_LOGNAME, stdout=parsl.AUTO_LOGNAME):
    # assuming we fuzz with -trace, we can overcommit the decode jobs here
    print(f"trace: {inputs[0]}")
    check_inputs(inputs)
    return f"{RUNNER} cov {inputs[0]} -p {NUM_THREADS}"

@bash_app
def smatch(inputs=[], outputs=[], stderr=parsl.AUTO_LOGNAME, stdout=parsl.AUTO_LOGNAME):
    print(f"smatch: {inputs[0]}")
    check_inputs(inputs)
    return f"USE_GHIDRA={USE_GHIDRA} MAKEFLAGS='-j{NUM_THREADS}' {RUNNER} smatch {inputs[0]}"

@bash_app
def audit_kernel(inputs=[], outputs=[], stderr=parsl.AUTO_LOGNAME, stdout=parsl.AUTO_LOGNAME):
    print(f"audit: {inputs[0]}")
    check_inputs(inputs)
    # TODO thread limit broken - maybe re-implement the test-kernel.sh here?
    if os.path.exists(outputs[1]):
        print(f"Skipping audit_kernel task - output already exists: {outputs[1]}")
        return ""
    else:
        return f"MAKEFLAGS='-j{NUM_THREADS}' {RUNNER} audit {inputs[0]} {inputs[1]}"

def run_campaign(args, harness_dirs):
    # smatch audit
    sources = Path(os.environ.get('LINUX_GUEST'))
    audit_dir = CAMPAIGN_DIR/'audit_list'
    os.makedirs(audit_dir, exist_ok=True)
    global_smatch_warns = audit_dir/'smatch_warns.txt'
    global_smatch_list = audit_dir/'smatch_warns_annotated.txt'

    # audit based on TDX fuzzing template
    # this is required to run inside the kernel source tree
    config = DEFAULT_GUEST_CONFIG
    audit_job = audit_kernel(inputs=[pfile(audit_dir), pfile(config)], outputs=[pfile(global_smatch_warns), pfile(global_smatch_list)])
    audit_job.result() # wait to complete

    # # build kernels for each harness and prepare `target` dir
    # clean = mrproper(inputs=[pfile(sources)], outputs=[pfile(sources)])
    # clean.result() # wait for mrproper

    for harness in harness_dirs:
        build_dir = mkjobdir(harness, 'build')
        target_dir = harness/'target'
        target_files = [
                build_dir/'.config',
                build_dir/'vmlinux',
                build_dir/'System.map',
                build_dir/'arch/x86/boot/bzImage',
                global_smatch_warns,
                global_smatch_list ]

        job = build(inputs=[pfile(harness)], outputs=[pfile(build_dir)])
        job.result() # wait for build to be done

        os.makedirs(target_dir, exist_ok=True)
        for f in target_files:
            shutil.copy(f, target_dir)
        if not args.keep:
            shutil.rmtree(build_dir)

    fuzz_jobs = []
    for harness in harness_dirs:
        target_dir = harness/'target'
        jobdir = mkjobdir(harness, 'run')
        job = fuzz(inputs=[pfile(target_dir)], outputs=[pfile(jobdir)])
        fuzz_jobs.append(job)

    # wait for all build jobs to complete
    #[job.result() for job in fuzz_jobs]

    trace_jobs = []
    for job in fuzz_jobs:
        # wait for fuzz job, then process traces & launch smatch matching
        jobdir = job.outputs[0].result()
        job = trace(inputs=[jobdir])
        job.result()
        job = smatch(inputs=[jobdir, global_smatch_list])
        trace_jobs.append(job)

    # wait for all jobs to complete
    [job.result() for job in trace_jobs]

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
    global CAMPAIGN_DIR
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
    CAMPAIGN_DIR = Path(harness_dirs[0].parent)

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
