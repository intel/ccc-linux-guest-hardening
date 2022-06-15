# Smatch-based Static Analysis for tracking host inputs

Scripts and example results for Smatch static analysis of the Linux kernel.

## Setup

Ensure you sourced the environment:

```shell
source ../../.env
```

If the environment file is missing, check the main [README](https://github.com/intel/ccc-linux-guest-hardening/blob/master/README.md) for installation instructions.

## Usage

Assuming the above smatch source code location is in `~/smatch` folder,
follow the instructions in [Our documentation](https://intel.github.io/ccc-linux-guest-hardening-docs/tdx-guest-hardening.html#applying-code-audit-results-to-different-kernel-trees)
to perform a smatch run for your kernel source tree and filter the results
using `./bkc/audit/process_smatch_output.py` and `./bkc/audit/transfer_results.py`
scripts.
