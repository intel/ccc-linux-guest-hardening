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
from pathlib import Path

import parsl
from parsl.app.app import python_app, bash_app
from parsl.data_provider.files import File

from parsl.config import Config
from parsl.executors.threads import ThreadPoolExecutor

#
# Configuration
#

# Log to screen
parsl.set_stream_logger(level=parsl.logging.INFO)

# Log to file
#parsl.set_file_logger(FILENAME, level=logging.DEBUG)

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
CAMPAIGN_DIR = Path("/home/steffens/data/test/")
DEFAULT_GUEST_CONFIG = BKC_ROOT/'bkc/kafl/linux_kernel_tdx_guest.config'
USE_GHIDRA=0 # use ghidra for gen_addr2line.sh?

#
# Helpers
#
def check_inputs(inputs):
    for f in inputs:
        if not os.path.exists(f):
            raise parsl.app.errors.ParslError(f"Missing input file {f}")

def mkjobdir(label):
    job_root = CAMPAIGN_DIR/'run'
    os.makedirs(job_root, exist_ok=True)
    tmpdir = tempfile.mkdtemp(dir=job_root, prefix=f"{label}_")
    os.chmod(tmpdir, 0o755)
    return Path(tmpdir)

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
    return f"MAKEFLAGS='-j{NUM_THREADS}' {RUNNER} build {inputs[0]}"

@bash_app
def fuzz(inputs=[], outputs=[], stderr=parsl.AUTO_LOGNAME, stdout=parsl.AUTO_LOGNAME):
    print(f"fuzz: {inputs[0]}")
    check_inputs(inputs)
    return f"KAFL_WORKDIR={outputs[0]} {RUNNER} run {inputs[0]} --abort-exec 100 -p {NUM_WORKERS}"

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
    return f"cp {inputs[1]} {inputs[0]}/target/smatch_warns.txt; USE_GHIDRA={USE_GHIDRA} MAKEFLAGS='-j{NUM_THREADS}' {RUNNER} smatch {inputs[0]}"

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

#
# Actual pipeline starts here
#
def pipeline(harness_dirs):
    jobs = []

    # smatch audit
    sources = Path(os.environ.get('LINUX_GUEST'))
    target = CAMPAIGN_DIR/'smatch'
    os.makedirs(target, exist_ok=True)
    global_smatch_warns = target/'smatch_warns.txt'
    global_smatch_list = target/'smatch_warns_annotated.txt'

    # audit based on TDX fuzzing template
    config = DEFAULT_GUEST_CONFIG
    audit_job = audit_kernel(inputs=[File(str(target)), File(str(config))], outputs=[File(str(global_smatch_warns)), File(str(global_smatch_list))])
    audit_job.result() # wait to complete
    clean = mrproper(inputs=[File(str(sources))], outputs=[File(str(sources))])
    clean.result() # wait for mrproper

    # harness builds
    for harness in harness_dirs:
        target=harness/'build'
        job = build(inputs=[File(str(harness))], outputs=[File(str(target))])
        jobs.append(job)

    # wait for all build jobs to complete
    [job.result() for job in jobs]

    fuzz_jobs = []
    for harness in harness_dirs:
        target = harness/'build'
        jobdir = mkjobdir(harness.name)
        job = fuzz(inputs=[File(str(target))], outputs=[File(str(jobdir))])
        fuzz_jobs.append(job)

    # wait for all build jobs to complete
    #[job.result() for job in jobs]

    for job in fuzz_jobs:
        jobdir = job.outputs[0].result()
        smatch_match = Path(jobdir)/'traces/smatch_match.lst'
        trace_out = Path(jobdir)/'traces/edges_uniq.lst'

        # start smatch once the corresponding edges_uniq.lst is done
        job = trace(inputs=[jobdir], outputs=[File(str(trace_out))])
        job = smatch(inputs=[jobdir, global_smatch_list, job.outputs[0]], outputs=[File(str(smatch_match))])
        jobs.append(job)

    # wait for all jobs to complete
    [job.result() for job in jobs]

if __name__ == "__main__":

    harness_dirs = list()
    for harness in CAMPAIGN_DIR.glob('**/kafl.yaml'):
        print(f"Identified harness directory: {harness.parent}")
        harness_dirs.append(harness.parent)

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

    pipeline(harness_dirs)
