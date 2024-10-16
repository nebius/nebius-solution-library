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

version=$(echo "${VERSION}" | tr '.' '_' | tr '-' '_')

mkdir -p releases
tarball="releases/soperator_tf_${version}.tar.gz"
if [ ! -f "$tarball" ] || [ -n "$force" ]; then
  tar -czf "$tarball" \
    installations \
    modules \
    test \
    README.md \
    ../LICENSE
  echo "$(pwd)/$tarball created."
fi
