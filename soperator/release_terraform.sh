#!/bin/bash

set -e

VERSION="${VERSION:?VERSION not set}"

usage() { echo "usage: ${0} [-f] [-h]" >&2; exit 1; }

while getopts fh flag
do
  case "${flag}" in
    f) force=1;;
    h) usage;;
    *) usage;;
  esac
done

mkdir -p releases
tarball="releases/soperator-tf-${VERSION}.tar.gz"
if [ ! -f "$tarball" ] || [ -n "$force" ]; then
  echo "Creating $tarball ..."
  pushd ..
  tar -czf "soperator/$tarball" \
    modules/gpu-operator \
    modules/network-operator \
    modules/nfs-server \
    soperator/installations \
    soperator/modules \
    soperator/test \
    soperator/README.md \
    LICENSE
  popd
  echo "Created $tarball ."
fi
