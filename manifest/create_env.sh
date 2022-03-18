# Generate a .env file to be sourced by pipenv
# If you don't use west, customize .env for your own repo locations.

if ! which west > /dev/null; then
	echo "Could not find west. Run this script from within the west workspace and python venv."
	exit -1
fi

if ! west list manifest > /dev/null; then
	echo "Failed to locate West manifest - not initialized?"
	exit -1
fi

# silence missing Zephyr install?
if ! west list zephyr > /dev/null 2>&1; then
   if ! west config zephyr.base > /dev/null; then
	   west config zephyr.base not-using-zephyr
   fi
fi

BKC_ROOT=$(west topdir)

echo BKC_ROOT=$BKC_ROOT
echo LINUX_GUEST=$(west list -f {abspath} linux-guest)
echo LINUX_HOST=$(west list -f {abspath} linux-host)
echo TDVF_ROOT=$(west list -f {abspath} tdvf)
echo SMATCH_ROOT=$(west list -f {abspath} smatch)

echo KAFL_ROOT=$(west list -f {abspath} kafl)
echo QEMU_ROOT=$(west list -f {abspath} qemu)
echo LIBXDC_ROOT=$(west list -f {abspath} libxdc)
echo CAPSTONE_ROOT=$(west list -f {abspath} capstone)
echo RADAMSA_ROOT=$(west list -f {abspath} radamsa)
echo PACKER_ROOT=$(west list -f {abspath} nyx-packer)

# default kAFL workdir + config
echo KAFL_CONFIG_FILE=$BKC_ROOT/bkc/kafl/kafl_config.yaml
echo KAFL_WORKDIR=/dev/shm/${USER}_tdfl
