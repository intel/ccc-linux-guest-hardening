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

## kAFL Fuzzer

### 1. Install kAFL

- Follow [kAFL Installation Steps](bkc/kafl/README.md#Installation)
- Run a [Boot Fuzzing Example](bkc/kafl/README.md#Linux-Boot-Fuzzing)
- Familiarize yourself with [kAFL Fuzzer Status and Tools](https://github.com/IntelLabs/kAFL/#understanding-fuzzer-status)

### 2. Simple Smatch Coverage Report
As explained earlier, we use smatch to statically obtain points that
potentially consume host input, which is what we want to reach through fuzzing.
Smatch produces a file called `$LINUX_GUEST/smatch_warns.txt`.

If you have succesfully ran a fuzzing campaign, you can gather the coverage and match this coverage against smatch using the following commands:
```shell
echo $KAFL_WORKDIR
./bkc/kafl/fuzz.sh cov $KAFL_WORKDIR
./bkc/kafl/fuzz.sh smatch $KAFL_WORKDIR
```

### 3. (Optional/ More advanced) Detailed Smatch Coverage & Batch-Running Harnesses
The above method matches your coverage against the input points identified by
smatch. We have included a tool called [smatcher](bkf/coverage/smatcher), which
can aggregate coverage over multiple campaigns and match it against an annotated `smatch_warns.txt`.

First make sure you have installed smatcher. In your kAFL virtualenv (do `make env` if you have not activate dit yet):
```shell
cd bkc/coverage/smatcher && pip install .
```
Now you should have the `smatcher` tool installed.

When using smatcher, you typically want to match against an annotated
`smatch_warns.txt` so that you can break down the coverage by category (such as
'trusted' or 'excluded'). You can transfer existing results to the
`smatch_warns.txt` generated in earlier steps. In the following example we will
transfer results from the sample file we have provided for Linux 5.15-rc1:
`bkc/audit/sample_output/5.15-rc1/smatch_warns_5.15_tdx_allyesconfig_filtered_results_analyzed`.


To do filtering/ processing and transfer existing smatch results:
```
export SMATCH_RESULTS=~/bkc/audit/sample_output/5.15-rc1/smatch_warns_5.15_tdx_allyesconfig_filtered_results_analyzed
cd $LINUX_GUEST
$BKC_ROOT/bkc/audit/scripts/process_smatch_output.py smatch_warns.txt
$BKC_ROOT/bkc/audit/scripts/transfer_results.py $SMATCH_RESULTS smatch_warns.txt.filtered
mv smatch_warns.txt smatch_warns.txt.bak
mv smatch_warns.txt.analyzed smatch_warns.txt
```
You should now have a `smatch_warns.txt` with the annotated/ audited entries for your target kernel.

After doing these steps, it is now possible to generate a detailed report of your campaign using smatcher:
```shell
smatcher -s $LINUX_GUEST/smatch_warns.txt $KAFL_WORKDIR
```


For convenience, we have included a script `bkc/kafl/run_experiments.py`, which can
automatically run large-scale experiments for all our harnesses.

To run all harnesses and store the resulting data in the folder `results` do:
```shell
bkc/kafl/run_experiments.py run $LINUX_GUEST results
```
Hint: you can parallelize the campaigns using the `-p` flag. To have the script
gather the coverage for you after finishing the campaigns, set the `-c` flag.

To summarize the aggregated results of your campaign, do something like:
```shell
smatcher -s $LINUX_GUEST/smatch_warns.txt --combine-cov-files results/*
```
