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
#parsl.set_stream_logger(level=parsl.logging.INFO)

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

BKC_ROOT=Path(os.environ.get('BKC_ROOT'))
RUNNER=BKC_ROOT/'bkc/kafl/fuzz.sh'
CAMPAIGN_DIR=Path("/home/steffens/data/test/")

NCPU=72        # available vCPUs
NUM_WORKERS=16 # kAFL workers (max 1 per vCPU)
NUM_THREADS=32 # SW threads to schedule (can to overcommit)
NUM_PIPES=max(1,(NCPU-2)//NUM_WORKERS) # concurrent pipelines

# use local python threads for spawning tasks in a pipeline
local_threads = Config(
    executors=[
        ThreadPoolExecutor(
            max_threads=NUM_PIPES,
            label='local_threads'
        )
    ]
)
parsl.load(local_threads)

#
# Helpers
#
def check_inputs(inputs):
    for f in inputs:
        if not os.path.exists(f):
            raise parsl.app.errors.ParslError(f"Missing input file {f}")

def mkjobdir(harness):
    job_root = CAMPAIGN_DIR/'run'
    label = harness.name + "_"
    os.makedirs(job_root, exist_ok=True)
    tmpdir = tempfile.mkdtemp(dir=job_root, prefix=label)
    #subprocess.run(f"chmod a+rx {tmpdir}", shell=True, stdout=out_stdout, stderr=out_stderr)
    os.chmod(tmpdir, 0o755)
    return tmpdir

##
# Task wrappers
##
@bash_app
def build(inputs=[], outputs=[], stderr=parsl.AUTO_LOGNAME, stdout=parsl.AUTO_LOGNAME):
    print(f"make: {inputs[0]}")
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
def smatch(inputs=[], outputs=[]):
    print(f"smatch: {inputs[0]}")
    check_inputs(inputs)
    return f"MAKEFLAGS='-j{NUM_THREADS}' {RUNNER} smatch {inputs[0]}"

@bash_app
def audit(inputs=[], outputs=[]):
    check_inputs(inputs)
    # TODO broken - maybe re-implement the test-kernel.sh here?
    return f"LINUX_GUEST={inputs[0]} MAKEFLAGS='-j{NUM_THREADS}' make -C {BKC_ROOT}/bkc/audit"

#
# Actual pipeline starts here
#
def pipeline():
    harnesses = list()
    for harness in CAMPAIGN_DIR.glob('**/kafl.yaml'):
        print(f"Identified harness directory: {harness.parent}")
        harnesses.append(harness.parent)

    jobs = []
    for harness in harnesses:
        target=harness/'build'
        job = build(inputs=[File(str(harness))], outputs=[File(str(target))])
        jobs.append(job)


    # wait for all build jobs to complete
    [job.result() for job in jobs]

    job_dirs = []
    for harness in harnesses:
        target=str(harness/'build')
        jobdir = mkjobdir(harness)
        job = fuzz(inputs=[File(target)], outputs=[File(jobdir)])
        jobs.append(job)
        job_dirs.append(jobdir)

    # wait for all build jobs to complete
    [job.result() for job in jobs]

    for job in job_dirs:
        jobdir = Path(job)
        trace_out = jobdir/'traces/edges_uniq.lst'

        job = trace(inputs=[File(str(jobdir))], outputs=[File(str(trace_out))])
        jobs.append(job)
        job.result()

        smatch_match = jobdir/'traces/smatch_match.lst'
        smatch_warns = jobdir/'/target/smatch_warns.lst'

        job = smatch(
                inputs=[File(str(jobdir)),
                    File(str(smatch_warns)),
                    File(str(trace_out))],
                outputs=[File(str(smatch_match))])
        jobs.append(job)

    [job.result() for job in jobs]


if __name__ == "__main__":
    pipeline()
