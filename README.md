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

```shell
echo $KAFL_WORKDIR
./bkc/kafl/fuzz.sh cov $KAFL_WORKDIR
./bkc/kafl/fuzz.sh smatch $KAFL_WORKDIR
```

### 3. Batch-Running Harnesses & Detailed Smatch Coverage

__TODO:__
- explain what this does and provide a single-campaign example
- expand harness descriptions to document basic performance and known issues

```shell
./bkc/kafl/run_experiments.sh ....
```
