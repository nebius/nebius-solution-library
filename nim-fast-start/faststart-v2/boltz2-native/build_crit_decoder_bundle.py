#!/usr/bin/env python3
"""Build the reviewed CRIU ``crit`` Python bundle from the released sources zip."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path


SOURCE_ARCHIVE_SHA256 = (
    "1f2a5a3f3b393feb57f18331f4af1284ea3b7883fadc2f8b2da70291fc1e0040"
)
CRIU_COMMIT = "91d552257809d0e5c7148190e9aa0372f13b76a0"
SOURCE_ROOT = "sources/native/criu/"


class BundleError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def selected_entries(archive: zipfile.ZipFile) -> list[tuple[str, bytes]]:
    result: list[tuple[str, bytes]] = []
    for info in archive.infolist():
        source = info.filename
        destination: str | None = None
        if source == SOURCE_ROOT + "COPYING":
            destination = "COPYING"
        elif source.startswith(SOURCE_ROOT + "crit/crit/") and source.endswith(".py"):
            destination = source.removeprefix(SOURCE_ROOT + "crit/")
        elif source.startswith(SOURCE_ROOT + "lib/pycriu/") and source.endswith(".py"):
            destination = source.removeprefix(SOURCE_ROOT + "lib/")
        if destination is None:
            continue
        mode = info.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if info.is_dir() or (file_type and not stat.S_ISREG(mode)):
            raise BundleError(f"selected source is not a regular file: {source}")
        result.append((destination, archive.read(info)))
    result.sort(key=lambda item: item[0].encode("utf-8"))
    names = [name for name, _ in result]
    if len(names) != len(set(names)):
        raise BundleError("decoder bundle contains duplicate destination paths")
    required = {
        "COPYING",
        "crit/__init__.py",
        "crit/__main__.py",
        "pycriu/__init__.py",
        "pycriu/images/images.py",
        "pycriu/images/mnt_pb2.py",
        "pycriu/images/regfile_pb2.py",
        "pycriu/images/mm_pb2.py",
        "pycriu/images/fs_pb2.py",
        "pycriu/images/ghost_file_pb2.py",
        "pycriu/images/remap_file_path_pb2.py",
    }
    if not required <= set(names):
        raise BundleError(f"decoder source archive is incomplete: {sorted(required-set(names))}")
    return result


def build(source_archive: Path, output: Path) -> None:
    if source_archive.is_symlink() or not source_archive.is_file():
        raise BundleError("source archive must be a regular non-symlink file")
    if sha256_file(source_archive) != SOURCE_ARCHIVE_SHA256:
        raise BundleError("released sources zip SHA-256 changed")
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise BundleError("output must be absent in an existing directory")
    with zipfile.ZipFile(source_archive) as archive:
        try:
            head = archive.read(SOURCE_ROOT + ".git/HEAD").decode("ascii").strip()
        except (KeyError, UnicodeDecodeError) as exc:
            raise BundleError("sources zip lacks the CRIU commit marker") from exc
        if head != CRIU_COMMIT:
            raise BundleError("sources zip CRIU commit changed")
        entries = selected_entries(archive)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".partial", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as tar:
                    for name, payload in entries:
                        info = tarfile.TarInfo(name)
                        info.size = len(payload)
                        info.mode = 0o644
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        info.mtime = 0
                        tar.addfile(info, io.BytesIO(payload))
            raw.flush()
            os.fsync(raw.fileno())
        os.link(temporary, output, follow_symlinks=False)
        temporary.unlink()
        parent_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.source_archive, args.output)
    except (BundleError, OSError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
