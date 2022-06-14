<h1 align="center">
  <br>Linux Security Hardening for Confidential Compute</br>
</h1>

<p align="center">
  <a href="https://github.com/Wenzel/ccc-linux-guest-hardening/actions/workflows/ci.yml">
    <img src="https://github.com/Wenzel/ccc-linux-guest-hardening/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
</p>

This project contains tools, scripts, and best-known-configurtion (BKC) for
Linux guest kernel hardening in the context of Confidential Cloud Computing threat
model.

Project overview:

```
- bkc/
  - audit/           # threat surface enumaration using static analysis
  - kafl/            # configs and tools for Linux fuzzing with kAFL
  - syzkaller/       # configs and tools for generating guest activity with Syzkaller
  - coverage/        # tools for matching coverage and trace data against audit list
- manifest/west.yml  # manifest of required sub-components
```


## Getting Started

### 1. Clone repo and create new workspace

We use Python `pipenv` and `west` repo management to manage the installation.
Clone this repo to a new directory and run `make env` to initialize your workspace:

```shell
git clone $this_repo_url ~/tdx
cd ~/tdx
make env  # create + enter Python venv; initialize west
```

For any new session, run `make env` again to initialize the Python environment
and source the .env file. All subsequent steps assume an active workspace.

### 2. Fetch or update sub-modules:

Use `west` to fetch or update one or more sub-repos. The complete list of active
repos can be viewed with `west list`. For fuzzing, download everything:

```shell
west update smatch linux-guest  # just Smatch audit analysis
west update                     # everything for fuzzing & analysis
```

See
[west basics](https://docs.zephyrproject.org/latest/guides/west/basics.html#west-basics)
for introduction to west.

### 3. Generate Smatch audit list

This generates a file `smatch_warns.txt` in the target folder, containing the
list of code locations found to consume potentially malicious input by an
untrusted hypervisor. This list should be generated once for the desired Linux
kernel code and configuration to be audited or fuzzed:

```shell
cp ./bkc/kafl/linux_kernel_tdx_guest.config $LINUX_GUEST/.config
make -C $LINUX_GUEST prepare
make -C ./bkc/audit
```

## Basic kAFL Operation

### 1. Install kAFL

- Follow [kAFL Installation Steps](bkc/kafl/README.md#Installation)
- Run a [Boot Fuzzing Example](bkc/kafl/README.md#Linux-Boot-Fuzzing)
- Familiarize yourself with [kAFL Fuzzer Status and Tools](https://github.com/IntelLabs/kAFL/#understanding-fuzzer-status)

### 2. Smatch Coverage Report

As explained earlier, we use smatch to statically obtain points that
potentially consume host input, which is what we want to reach through fuzzing.
Smatch produces a file called `$LINUX_GUEST/smatch_warns.txt`.

If you have successfully ran a fuzzing campaign, you can gather the coverage and
match this coverage against smatch using the following commands:

```shell
echo $KAFL_WORKDIR
./bkc/kafl/fuzz.sh cov $KAFL_WORKDIR
./bkc/kafl/fuzz.sh smatch $KAFL_WORKDIR
```

## Batch-Running Campaigns and Smatch Coverage

For full validation of a target, we run several fuzzing harnesses and compare
their aggregated coverage against the smatch audit list. Moreover, an annotated
audit list based on previous manual review can be used to directly prioritize
any gaps identified in the aggregated coverage report.

### 1. Generate annotated Smatch Audit List

If not already done, generate an annotated smatch report for your desired Linux
guest kernel version and configuration.  The following script automatically
generates a report for the kernel located `$LINUX_GUEST` and transfers
annotations from a [previously performed manual audit for Linux
5.15-rc1](bkc/audit/sample_output/5.15-rc1/smatch_warns_5.15_tdx_allyesconfig_filtered_results_analyzed).
For additional background, see [applying code audit results](https://intel.github.io/ccc-linux-guest-hardening-docs/tdx-guest-hardening.html#applying-code-audit-results-to-different-kernel-trees).

```shell
make -C $LINUX_GUEST prepare
make -C ./bkc/audit
mv $LINUX_GUEST/smatch_warns_annotated.txt $LINUX_GUEST/smatch_warns.txt
```

Note that the `annotated` smatch report is moved to `smatch_warns.txt`,
where it will be picked up by fuzzer and coverage analysis tools.

### 2. Batch-Run Campaigns with Coverage

The included `run_experiments.py` can be used to automate the execution of
campaigns with best-known configuration for each harness.

Running all defined harnesses can take a few days, so you may want to start with
a single test case to validate the overall process and setup first.

Execution of campaigns can be parallelized using the `-p` flag, and
automated/fast coverage collection can be enabled using `-c`.

To run the configured harnesses and store the resulting data in the folder `~/results`:

```shell
./bkc/kafl/run_experiments.py -p 4 run -c $LINUX_GUEST ~/results
```

Note: Coverage collection uses Ghidra to reconstruct full traces from PT dumps.
Install Ghidra using kAFL helper script: `$KAFL_ROOT/scripts/ghidra_install.sh`.

### 3. Generate Aggregated Smatch Coverage Report

The [smatcher](bkc/coverage/smatcher) tool aggregates coverage over multiple
campaigns and matches it against an annotated audit list. Install smatcher to
your python environment like this:

```shell
make env    # enable virtualenv if not active
pip install ./bkc/coverage/smatcher
```

To generate a smatch coverage report for a single campaign:
```shell
smatcher -s $LINUX_GUEST/smatch_warns.txt $KAFL_WORKDIR
```

To generate an aggregated report, use something like:
```shell
smatcher -s $LINUX_GUEST/smatch_warns.txt --combine-cov-files results/*
```
