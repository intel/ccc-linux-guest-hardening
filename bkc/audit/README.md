# Smatch-based Static Analysis for tracking host inputs

Scripts and example results for Smatch static analysis of the Linux kernel.

## Setup
Ensure your installation is complete, and you activate the environment by `make env` before using smatch.

A successful installation will place smatch source code is in `smatch/` directory.

If the environment file is missing, check the main [README](https://github.com/intel/ccc-linux-guest-hardening/blob/master/README.md) for system requirements and installation [instructions](https://github.com/intel/ccc-linux-guest-hardening/blob/master/docs/getting_started.md#2-installation).

## Usage
Follow the [tutorial](https://github.com/intel/ccc-linux-guest-hardening/blob/master/docs/generate_smatch_audit_list.md) 
to perform a smatch run for your kernel source tree and filter the results
using `bkc/audit/process_smatch_output.py` and `bkc/audit/transfer_results.py`
scripts.

Visit our [documentation](https://intel.github.io/ccc-linux-guest-hardening-docs/tdx-guest-hardening.html#applying-code-audit-results-to-different-kernel-trees) for more detail.
