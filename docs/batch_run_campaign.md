# Batch-Running Campaigns and Smatch Coverage

For full validation of a target, we run several fuzzing harnesses and compare
their aggregated coverage against the smatch audit list. Moreover, an annotated
audit list based on previous manual review can be used to directly prioritize
any gaps identified in the aggregated coverage report.

## 1. Generate annotated Smatch Audit List

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

## 2. Batch-Run Campaigns with Coverage

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

## 3. Generate Aggregated Smatch Coverage Report

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
