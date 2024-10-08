#!/bin/bash

usage() { echo "usage: ${0} -u <ssh_user> -k <path_to_ssh_key> -a <address> [-p <port>] [-h]" >&2; exit 1; }

while getopts u:k:a:p:n:h flag
do
    case "${flag}" in
        u) user=${OPTARG};;
        k) key=${OPTARG};;
        a) address=${OPTARG};;
        p) port=${OPTARG};;
        h) usage;;
        *) usage;;
    esac
done

if [ -z "$user" ] || [ -z "$key" ] || [ -z "$address" ]; then
    usage
fi

if [ -z "$port" ]; then
    port=22
fi

echo "Transferring files as user '${user}' with key '${key}' to ${address}:${port}..."
scp \
  -i "${key}" \
  -P "${port}" \
  -r \
  ./mlperf-gpt3/* \
  "${user}"@"${address}":/opt/mlperf-gpt3

echo "Done"
