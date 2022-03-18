# kAFL trace line coverage/ smatch match tool
This tool (`fast_matcher`) can gather the line coverage and smatch
coverage for kAFL campaigns.

## How to build
`cargo build --release`

## How to use
Run `target/release/fast_matcher` to print the tool usage.

In short, the tool takes one main argument, namely the path to the kAFL campaign workdir. 

Additionally, the tool supports some other options:

* `-a`, print full line coverage, not just smatch report matches (recommended)
* `-s /path/to/smatch_warns.txt`, provide a custom smatch file
* `-f`, also include all inlined location line numbers
* `-m`, print the matching lines from the smatch report, rather than just the line coverage
* `-p npar`, parallelize the workload, where `npar` is the number of workers

For example, to save the full line coverage for a campaign as
traces/linecov.lst, while in a kAFL workdir do the following:

`fast_matcher -a -s ~/tdx/linux-guest/smatch_warns.txt -f -p$(nproc) /dev/shm/$USER_tdfl > traces/linecov.lst`
