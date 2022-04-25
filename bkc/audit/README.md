# Smatch-based Static Analysis for tracking host inputs

Scripts and example results for Smatch static analysis of the Linux kernel.

## Installation 

1. Download smatch source code from  [smatch repo](https://repo.or.cz/w/smatch.git)
2. Apply `./0001-check_host_input-add-a-pattern.patch` to the source code
tree.
3. Follow the instructions in [smatch documentation](https://repo.or.cz/smatch.git/blob/HEAD:/Documentation/smatch.txt) to install
smatch dependencies and compile smatch.

## Usage

Assuming the above smatch source code location is in `~/smatch` folder,
follow the instructions in [Our documentation](https://intel.github.io/ccc-linux-guest-hardening-docs/tdx-guest-hardening.html#applying-code-audit-results-to-different-kernel-trees)
to perform a smatch run for your kernel source tree and filter the results
using `./bkc/audit/process_smatch_output.py` and `./bkc/audit/transfer_results.py`
scripts.


