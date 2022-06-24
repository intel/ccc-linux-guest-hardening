# Generate Smatch audit list

This generates a file `smatch_warns.txt` in the target folder, containing the
list of code locations found to consume potentially malicious input by an
untrusted hypervisor. This list should be generated once for the desired Linux
kernel code and configuration to be audited or fuzzed:

```shell
cp ./bkc/kafl/linux_kernel_tdx_guest.config $LINUX_GUEST/.config
make -C $LINUX_GUEST prepare
make -C ./bkc/audit
```

## Smatch Coverage Report

As explained earlier, we use smatch to statically obtain points that
potentially consume host input, which is what we want to reach through fuzzing.

Smatch produces a file called `$LINUX_GUEST/smatch_warns.txt`.

If you have successfully ran a fuzzing campaign, you can gather the coverage and
match this coverage against smatch using the following commands:

```shell
echo $KAFL_WORKDIR
./bkc/kafl/fuzz.sh cov $KAFL_WORKDIR
./bkc/kafl/fuzz.sh smatch $KAFL_WORKDIR
```