#!/bin/bash

OUTPUT="../initrd.cpio.gz"

test -n "$1" && OUTPUT=$(realpath $1)

pushd $(dirname $0) > /dev/null
find . -print0 | cpio --null --create --format=newc | gzip --best  > $OUTPUT
popd > /dev/null
