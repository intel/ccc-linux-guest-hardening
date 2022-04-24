# Linux Security Hardening for Confidential Compute

This project contains tools, scripts, and best-known-configurtion (BKC) for
Linux guest kernel hardening in context of Confidential Cloud Computing threat
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
untrusted hypervisor. This list should be generated for the desired Linux kernel
code and configuration to be audited or fuzzed:

```shell
cp ./bkc/kafl/linux_kernel_tdx_guest.config $LINUX_GUEST/.config
make -C $LINUX_GUEST prepare
./bkc/audit/gen_smatch_warns.sh $LINUX_GUEST
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

If you have succesfully ran a fuzzing campaign, you can gather the coverage and match this coverage against smatch using the following commands:
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

In the following we first generate a smatch audit list (`smatch_warns.txt`) for
a given Linux guest kernel and then transfer audit annotations from an
existing [sample audit provided for Linux
5.15-rc1](bkc/audit/sample_output/5.15-rc1/smatch_warns_5.15_tdx_allyesconfig_filtered_results_analyzed).

```shell
SMATCH_BASE=$BKC_ROOT/bkc/audit/sample_output/5.15-rc1/smatch_warns_5.15_tdx_allyesconfig_filtered_results_analyzed
./bkc/audit/gen_smatch_warns.sh $LINUX_GUEST
./bkc/audit/transfer_results.py $SMATCH_BASE $LINUX_GUEST/smatch_warns.txt.filtered
mv smatch_warns.txt.analyzed $LINUX_GUEST/smatch_warns.txt
```

The resulting annotated audit list (`smatch_warns.txt`) is specific to the
$LINUX\_GUEST version and configuration, but includes, as far as possible,
automatically transferred annotations from a previous manual kernel audit.

### 2. Batch-Run Campaigns with Coverage

The included `run_experiments.py` can be used to automate the execution of
campaigns with best-known configuration for each harness.

Running all defined harnesses can take a few days, so you may want to start with
a single test case to validate the overall process and setup first.

Execution of campaigns can be parallelized using the `-p` flag, and
automated/fast coverage collection can be enabled using `-c`.

To run the configured harnesses and store the resulting data in the folder `~/results`:

```shell
./bkc/kafl/run_experiments.py run -c -p 4 $LINUX_GUEST ~/results
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
