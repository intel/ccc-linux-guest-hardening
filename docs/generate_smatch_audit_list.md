# Generate Smatch audit list

This generates a file `smatch_warns.txt` in the target folder, containing the
list of code locations found to consume potentially malicious input by an
untrusted hypervisor. This list should be generated once for the desired Linux
kernel code and configuration to be audited or fuzzed:


First, ensure a config file for your guest kernel, e.g.,
```shell
cp ./bkc/kafl/linux_kernel_tdx_guest.config $LINUX_GUEST/.config 
```

The smatch audit lists should be automatically generated when initialize basic campaign/fuzzing assets via `make prepare`.  

Or, you may manually execute the helper script `bkc/audit/smatch_audit.sh` to perform generation, filtering, and annotation/transfer steps for smatch audit lists:
```shell
  Usage: ./bkc/audit/smatch_audit.sh <dir> <config>
  
  Where:
    <dir>     - output directory for storing smatch results
    <config>  - kernel config to be used in build/audit
```

## Smatch Coverage Report

As explained earlier, we use smatch to statically obtain points that
potentially consume host input, which is what we want to reach through fuzzing.

Smatch produces a file called `smatch_warns.txt`.

If you have successfully ran a fuzzing campaign, you can gather the coverage and
match this coverage against smatch using the `smatch` option with the kAFL launcher `bkc/kafl/fuzz.sh`.  Here is a brief workflow:

```shell
# Assume the work directory is correctly set to $KAFL_WORKDIR

# Re-execute all payloads from $KAFL_WORKDIR/corpus/ and collect the individual trace logs to $KAFL_WORKDIR/trace/
bkc/kafl/fuzz.sh cov $KAFL_WORKDIR

# get addr2line and smatch_match results from traces
bkc/kafl/fuzz.sh smatch $KAFL_WORKDIR
```

Please refer to the [here](https://github.com/tz0/ccc-linux-guest-hardening/blob/master/docs/workflow_overview.md#12-kafl-launcher-bkckaflfuzzsh) for the detail usage of the `bkc/kafl/fuzz.sh` launcher options.