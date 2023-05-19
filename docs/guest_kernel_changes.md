# Patch Target Kernel for Fuzzing

Patching and code modification can be required when fuzzing a non-default guest kernel. This guide describes the related and recommended commits to make the target fuzzable.

## The Default Guest Kernel
You can check the ansible playbook [script](deploy/roles/guest/defaults/main.yml) for the source and the branch of the guest kernel used by default, e.g.,
```
guest_url: https://github.com/IntelLabs/kafl.linux
guest_revision: kafl/fuzz-6.0-2
```
All the patches we describe with commit IDs can be found in the above branch. A target guest kernel wants to apply multiple sets of patches from the below:

1. The CCC suite patches, implementing fuzzing hooks for KAFL, etc.
2. The TDX guest patches enable fuzzing functionalities
3. TDX functionality patches are recommended for fuzzing features
4. General TDX functionality patches

To ensure *the correct order of backporting*, apply patch sets 4 and 3 first, followed by patch set 2, and finally, apply patch set 1.

While patch set 3 is _not strictly needed_, it's highly recommended for the fuzzing campaign to become effeceint. Multiple patches from patch set 4 can also be required depending on different needs for fuzzing.


## Patch Set 1:
The commits in this set are needed as they construct the kAFL fuzzing facility ([kafl-agent.c](https://github.com/IntelLabs/kafl.linux/blob/kafl/fuzz-6.0-2/arch/x86/coco/tdx/kafl-agent.c)) on top of the below TDX fuzzing API. These commits also insert kAFL events to the kernel source for pre-defined fuzzing harnesses, implement debugging interfaces, etc.

The commits below start from the most recent:
- [08f4734ac0b25280584b6d6d6d41377bc6a31a3d](https://github.com/IntelLabs/kafl.linux/commit/08f4734ac0b25280584b6d6d6d41377bc6a31a3d) `Changes to make fuzzing deterministic`
- [c3e6917e357490d5aee22771a43c49dc9fb5465b](https://github.com/IntelLabs/kafl.linux/commit/c3e6917e357490d5aee22771a43c49dc9fb5465b) `Add fuzzing support for virtio subsystem and its drivers`
- [a997e6cb3fd1bc34c889c894b54ffebeb2b18a3d](https://github.com/IntelLabs/kafl.linux/commit/a997e6cb3fd1bc34c889c894b54ffebeb2b18a3d) `Add KAFL debugging options`
- [6025a85de087fcf2c54aa3f17d6bfe43f849f021](https://github.com/IntelLabs/kafl.linux/commit/6025a85de087fcf2c54aa3f17d6bfe43f849f021) `Add fuzzing harnesses`
- [9500fa680772278b63237b2fa51546d9e15bf6ba](https://github.com/IntelLabs/kafl.linux/commit/9500fa680772278b63237b2fa51546d9e15bf6ba) `Update tdx_fuzz api and add to kafl-agent`
- [852781a5425e174dd0ae537e0d3e7f750bb1c3a3](https://github.com/IntelLabs/kafl.linux/commit/852781a5425e174dd0ae537e0d3e7f750bb1c3a3) `x86/tdx: Add KAFL agent`


## Patch Set 2:
The following commits in this set are required as they enable the basic fuzzing functionalities for TDX, such as the input injection interface.
The commits below start from the most recent:

The commits below start from the most recent:
- [0ef8de9ba2bde71cfd67ea50abee094635aef3d3](https://github.com/IntelLabs/kafl.linux/commit/0ef8de9ba2bde71cfd67ea50abee094635aef3d3) `x86/tdx: Add CONFIG option for KVM SDV workarounds`
- [2b14aba6e07ec33791f58074392752cb2e4b10e5](https://github.com/IntelLabs/kafl.linux/commit/2b14aba6e07ec33791f58074392752cb2e4b10e5) `x86/tdx: Injection interface for fuzzer`
- [e1b2168d30f280d4fce9d1eead66db723d4ab033](https://github.com/IntelLabs/kafl.linux/commit/e1b2168d30f280d4fce9d1eead66db723d4ab033) `tdx: Document tdx failure_inject sysfs parameters`
- [447a34709b6bead1c6fc1de42076161ea17010a7](https://github.com/IntelLabs/kafl.linux/commit/447a34709b6bead1c6fc1de42076161ea17010a7) `x86/tdx: Add trace point for tdx fuzzer `
- [6a6ac61269e772906d5b0a1b1f4a6fcba10810b0](https://github.com/IntelLabs/kafl.linux/commit/6a6ac61269e772906d5b0a1b1f4a6fcba10810b0) `x86/tdx: Add error injection for TDCALLs`
- [0f7ff10537625881144a4b68751cff2131f098e1](https://github.com/IntelLabs/kafl.linux/commit/0f7ff10537625881144a4b68751cff2131f098e1) `x86/tdx: Basic TDCALL fuzzing support`


## Patch Set 3:
The commits in this set are strongly recommended because these patches implement device filter support and add audited drivers into the allow list. TDX guests only require a small number of drivers. Confining fuzzing coverage only on the targeted threat surface increases the fuzzing effectiveness.

Without device filtering, all devices will be enabled in the guest per kernel config, and all probe functions of devices will be running and consuming fuzzing input. 

Several commits below start from the most recent:
- [d44d705f1a67598f2a21a1d6fb3412b27edee5a8](https://github.com/IntelLabs/kafl.linux/commit/d44d705f1a67598f2a21a1d6fb3412b27edee5a8) `tdx: Add basic pci config space filter`
- [b5812625f245fbcee0c97d9a431d0f7f2f0aea6d](https://github.com/IntelLabs/kafl.linux/commit/b5812625f245fbcee0c97d9a431d0f7f2f0aea6d) `x86/tdx: Add vsock to TDX device filter's allow list`
- [823cd8a09552342cacdf0867aa3768cddad8cd4b](https://github.com/IntelLabs/kafl.linux/commit/823cd8a09552342cacdf0867aa3768cddad8cd4b) `x86/tdx: Initialize subvendor/subdevice in "authorize_allow_devs" parser`
- [10057ea06b77a1eadea7ecffd38697af286d4820](https://github.com/IntelLabs/kafl.linux/commit/10057ea06b77a1eadea7ecffd38697af286d4820) `x86/tdx: Add cmdline option to force use of ioremap_shared`
- [eb79a5321a597632e4f395d13d6e5020a395546c](https://github.com/IntelLabs/kafl.linux/commit/eb79a5321a597632e4f395d13d6e5020a395546c) `ACPI: Initialize authorized attribute for confidential guest`
- [7b01db54da4746435e1e1865dd7e9cc609c1e064](https://github.com/IntelLabs/kafl.linux/commit/823cd8a09552342cacdf0867aa3768cddad8cd4b) `x86/tdx: Extend TDX filter to support ACPI bus`
- [ab62aea205a2af7bf5dd0ab31d269a1a93ee5a1b](https://github.com/IntelLabs/kafl.linux/commit/ab62aea205a2af7bf5dd0ab31d269a1a93ee5a1b) `x86/tdx: Allow TDEL ACPI table`
- [e0f687e6c5e475e828f29dbdc464d2820177fbb7](https://github.com/IntelLabs/kafl.linux/commit/e0f687e6c5e475e828f29dbdc464d2820177fbb7) `x86/tdx: Allow SVKL ACPI table`
- [a4239c1d285d2c73c87f565d122c43f7f663b908](https://github.com/IntelLabs/kafl.linux/commit/a4239c1d285d2c73c87f565d122c43f7f663b908) `x86/tdx: Add a command line option to add new ACPI tables to the filter`
- [6712f7b04ef884cc0c764ae69f5bd844cb9d1769](https://github.com/IntelLabs/kafl.linux/commit/6712f7b04ef884cc0c764ae69f5bd844cb9d1769) `x86/tdx: Limit the list of ACPI tables allowed`
- [4a120bbfa330d0d6e7653c2d6b25fe010919c40e](https://github.com/IntelLabs/kafl.linux/commit/4a120bbfa330d0d6e7653c2d6b25fe010919c40e) `ACPICA: Add ACPI table filter support`
- ... ...
- [58ca3febfac615f803b0d64d176f750bd34bf10f](https://github.com/IntelLabs/kafl.linux/commit/58ca3febfac615f803b0d64d176f750bd34bf10f) `x86/tdx: Implement port I/O filtering`
- [25a08580ddad94169732f917e5429361f7b6c0b9](https://github.com/IntelLabs/kafl.linux/commit/25a08580ddad94169732f917e5429361f7b6c0b9) `x86/tdx: Add command line option to disable TDX guest filter support`
- [4af4f6023239dfd0370b601c6c999368bc8b1021](https://github.com/IntelLabs/kafl.linux/commit/4af4f6023239dfd0370b601c6c999368bc8b1021) `x86/tdx: Add command line option to override device allow list`
- [7f8f03269925a391cebded5a705121352e5b0e1d](https://github.com/IntelLabs/kafl.linux/commit/7f8f03269925a391cebded5a705121352e5b0e1d) `x86/tdx: Add device filter support for x86 TDX guest platform`
- ... ...

For the full list of device filter commits and the latest updates, you may refer to the remote-tracking branch [guest-filter](https://github.com/intel/tdx/commits/guest-filter) and the branch [guest-hardening-filter](https://github.com/intel/tdx/commits/guest-hardening-filter) for additional changes related to TDX guest hardening.


## Patch Set 4:
General tdx patches for different guest functionalities are maintained and tested in the branch [guest-next](https://github.com/intel/tdx/commits/guest-next) from the Intel public [TDX](https://github.com/intel/tdx) repository. This branch is actively developed for updates and fixes and merged from multiple remote-tracking branches that separately works on TDX guest for different subjects. For instance, some needed changes come from the remote-tracking branch [guest-debug](https://github.com/intel/tdx/commits/guest-debug) in the tracepoint for tracing TDX guest virtual exceptions. 

You may cherry-pick patches and perform backporting when different functionalities are required or targeted. Note that these remote tracking branches are constantly updated, and most of the content of this branch is planned to be upstreamed.


## A Few Steps After Backporting
1. Link the new guest kernel to the CCC repository environmental variable `$LINUX_GUEST`, e.g., `export LINUX_GUEST=/new/guest-kernel`. You may also modify the environment setup script `env.sh` under the CCC root for a permanent change.
2. Follow this [step](getting_started.md#32-optional-build-smatch-cross-function-database-for-better-coverage-results) to reproduce the Smatch cross-function database and audit lists. This can also be done by re-run the [step](getting_started.md#31-prepare-global-baseline-assets-initrd-qemu-disk-image-sharedir) that prepares all global baseline assets.