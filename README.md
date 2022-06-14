<h1 align="center">
  <br>Linux Security Hardening for Confidential Compute</br>
</h1>

<p align="center">
  <a href="https://github.com/Wenzel/ccc-linux-guest-hardening/actions/workflows/ci.yml">
    <img src="https://github.com/Wenzel/ccc-linux-guest-hardening/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
</p>

This project contains tools, scripts, and _best-known-configuration_ (BKC) for
Linux guest kernel hardening in the context of Confidential Cloud Computing threat
model.

# Project overview:

In the [`bkc`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc) directory, you will find:

- [`audit`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/audit): threat surface enumaration using static analysis
- [`kafl`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/kafl): configs and tools for Linux fuzzing with kAFL
- [`syzkaller`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/syzkaller): configs and tools for generating guest activity with Syzkaller
- [`coverage`](https://github.com/intel/ccc-linux-guest-hardening/tree/master/bkc/coverage): tools for matching coverage and trace data against audit list

# Getting started

## Requirements

- `python3`
- `python3-venv`

~~~
sudo apt-get install python3 python3-venv
~~~

## Setup

Clone this repo to a new directory and run `make deploy` to initialize your workspace:

```shell
git clone https://github.com/intel/ccc-linux-guest-hardening ~/tdx
cd ~/tdx
```

This repository offers the possibility of local or remote installation.

In both cases, you will find in the installation directory:
- `.env` file: useful environment variables for your scripts
- `.venv` Python virtual environment: where kAFL fuzzer is installed

### Local

- installation directory: `<repo_root>/`

Run the deployment with:
~~~
make deploy
~~~

You will be prompted for your root password.
If you are using a _passwordless sudo_ setup, just skip this by pressing enter.

### Remote

- installation directory: `$HOME/ccc`

You will have to update the `deploy/inventory` file to describe your nodes, according to [Ansible's inventory guide](https://docs.ansible.com/ansible/latest/user_guide/intro_inventory.html).
Make sure to **remove** the first line:

~~~
localhost ansible_connection=local
~~~

And run the deployment:

~~~
make deploy
~~~

Note: if your nodes require a proxy setup, update the `group_vars/all.yml`.

## Activate the environment

When the installation is complete, make sure to source the environment file `.env` and activate the `.venv`:

```shell
source .env
source $KAFL_ROOT/.venv/bin/activate
```

# Kernel Hardening

Now that the necessary components are installed, you can pursue by one the following:

1. [Generate smatch audit list](./docs/generate_smatch_audit_list.md)
2. [Run kAFL boot and usermode harnesses](./bkc/kafl)
3. [Batch-Running Campaigns and Smatch Coverage](./docs/batch_run_campaign.md)
