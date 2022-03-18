# Smatcher.py: aggregate line coverage and match against smatch analysis

This script (smatcher.py) can aggregate the line coverage for multiple fuzzing
campaigns (kAFL or generic) and match the covered lines against a smatch static
analysis report.

The script prints out which smatch targets have been covered, and can show how
well particular functions are covered. Furthermore it shows some coverage
statistics (i.e., how many concern items have been reached, etc.).

# How to install
`pip install .`

# How to uninstall
`pip uninstall smatcher`

# Usage:
See `smatcher --help`

For example, to aggregate multiple kAFL campaigns stored in a folder `/Data`
and match this against the smatch report at
`~/tdx/linux-guest/smatch_warns.txt`, you can do:

`smatcher --stats --combine-cov-files -s ~/tdx/linux-guest/smatch_warns.txt --print-uncovered-concern -u /Data/*/`


# How to generate smatch_warns.txt
Download smatch and run `smatch_scripts/test_kernel.sh` in your target kernel work directory.
