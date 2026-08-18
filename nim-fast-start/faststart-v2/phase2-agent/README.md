# Generic one-shot Dynamo restore worker

This directory contains the complete source overlay, patch series, and
provenance needed to reproduce the one-shot worker used by the OpenFold2 native
restore path. Materialization and source verification are offline and always
start from the immutable Dynamo Git object
`f7f37be174d252590c4b56e25ff4262dd82466fd`.

The final worker is model-independent. Model, Pod, container, checkpoint,
artifact, and tool-bundle identities are supplied through its explicit
argument contract rather than compiled OpenFold2 constants.

## Source composition

`materialize_overlay.sh` archives the pinned Git object, applies these patches
in order, and then installs `overlay/`:

| Input | SHA-256 |
|---|---|
| `public-aio-toolchain.patch` | `de10a0609115589efb137186544c9d90a0fcc03616ef959376139c65ae9615bc` |
| `core-hardening.patch` | `260c1d9a7f192b8c0b25c924ab26b43a95ad599d38d3f367383e3e984aecfd11` |
| `compliance-closure.patch` | `32493e5da929a993976148124699f8abf99240c4ba486e6a01fda453c682ae68` |
| `source-archive-fix.patch` | `5dd45d97596bbdf068f33f0532fc71da1754c9eeb7d91f0abe547ac29f30bf0e` |
| normalized overlay tree | `c5a443ad574f77011a7e330b2759b651399fef87c9ef40010750ab509f2c886f` |
| `Dockerfile.restore-worker` | `f0fb42c68ad7bf8dd39e27a5e070a1613953e7ec2cac0f19027cbea63a509570` |

The patch series pins the compiler, CUDA helper, CRIU builder, runtime, CRIU
revision, cuda-checkpoint revision, Go dependency graph, SBOM inputs, and source
archive behavior. The overlay adds the one-shot worker plus its focused tests
and the namespace-FD pinning used during restore.

The exact component and image metadata is in `provenance.json`.

## Worker contract

The worker accepts one `restore` operation and exits after emitting one JSON
receipt. Before restore, it binds and revalidates:

- target namespace, Pod name and UID;
- container name, full containerd ID, immutable image ID, cgroup, Pod IP, and
  node;
- canonical API-defaulted PodSpec SHA-256 and run ID;
- checkpoint ID, artifact version and artifact-manifest SHA-256; and
- the SHA-256 of the baked `/snapshot-binaries.manifest`.

It injects the baked CRIU/CUDA tool bundle into the unmodified target mount
namespace. The OpenFold2 target therefore remains the exact NVIDIA image
digest; no derivative model image is required.

## Reproduce the source tree

```console
./materialize_overlay.sh \
  /path/to/dynamo-at-f7f37be \
  /tmp/dynamo-one-shot-worker
```

The destination must not exist. The script reads only the pinned Git object,
never untracked or dirty files from the source checkout.

## Build and test

From the materialized tree:

```console
cd /tmp/dynamo-one-shot-worker/deploy/snapshot

docker build --progress=plain --platform linux/amd64 \
  --target tester \
  --build-context operator=../operator \
  --build-context compliance=../../container/compliance .

docker build --progress=plain --platform linux/amd64 \
  --target agent \
  --build-context operator=../operator \
  --build-context compliance=../../container/compliance \
  --build-arg ENABLE_SOURCE_ARCHIVAL=true \
  --tag archvteams-2407-snapshot-agent:f7f37be-criu91d552 .
```

`Dockerfile.restore-worker` is an optional binary-only export target. The
runnable worker image is the patched upstream `agent` target because that
image also carries the matched CRIU, CUDA helper, plugins, libraries, legal
inventory, and `/snapshot-binaries.manifest`.

The image used for the successful OpenFold2 runs was:

```text
cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/snapshot-agent@sha256:31e1dacd18b99aec1ab7e8ec8c933f260c9dcec687938b40c44c61274f930d86
```

Its local OCI image ID was
`sha256:dc7806d8440c967fcf1efd713ec0a9bcb6496a7741f97fe65e28a66d66a91314`;
the worker binary SHA-256 was
`8873c760a1760c0dc3b3e331c7aedf879e7737ad11aed7f028513f057bbbee6e`;
and its tool-bundle manifest SHA-256 was
`04214d6f4d72fa59d5daa6168d8c63024b6ebe34c4876394e47e80319ef00c39`.

## Offline verification

```console
./verify_offline.sh /path/to/dynamo-at-f7f37be
```

The verifier checks the source object, patch hashes, materialized files,
dependency graph, Dockerfile pins, provenance JSON, and normalized overlay
hash. It makes no network, registry, cloud, or Kubernetes request. The final
upstream Go/tester suite passed before the image above was used in three
consecutive successful OpenFold2 restores.
