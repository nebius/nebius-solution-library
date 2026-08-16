# CRIU io_uring dump fix (unblocks newer /predict NIMs)

The newer BioNeMo NIMs (OpenFold3, Boltz2, MSA-Search) run an async HTTP server
that holds **io_uring** file descriptors. Stock CRIU 4.2 (and the earlier Phase-5
patched builds) abort their dump with:

```
Error (criu/parasite-syscall.c): Can't retrieve FDs from socket
Error (criu/cr-dump.c): Dump files (pid: N) failed with -22
```

## Root cause

CRIU drains a process's FDs through the parasite via `SCM_RIGHTS`. The kernel
(6.x) refuses to pass `anon_inode:[io_uring]` FDs over `SCM_RIGHTS`, so the
parasite (`criu/pie/parasite.c: drain_fds`) skips them and sends only the
remaining FDs, setting `args->nr_fds` to the reduced count.

**But the parasite runs on an injected *copy* of the args buffer** — its
write-back of the reduced `nr_fds` is never seen by the CRIU daemon. The daemon
(`parasite_drain_fds_seized`) therefore still expected the *original* count and
`recv_fds()` blocked/failed → `-22`.

Confirmed with instrumentation: `nr_fds=56 actual_nr=56` while the parasite had
sent only 54 (2 io_uring FDs skipped).

## The fix (`apply_iouring_drain_fix.py`)

Make the daemon independently compute how many FDs the parasite will send,
instead of trusting the non-visible write-back:

- `criu/parasite-syscall.c` — `parasite_drain_fds_seized` now takes the victim
  `pid`, `readlink`s `/proc/<pid>/fd/<fd>` for each drained FD, and counts the
  non-`[io_uring]` ones as the expected `recv_fds` count. Received FDs are mapped
  back to their original positions (the parasite preserves order), io_uring
  positions stay `-1`.
- `criu/include/parasite-syscall.h` — prototype gains `pid_t victim_pid`.
- `criu/files.c` — the sole caller passes `item->pid->real`.

No `inject_close`, no eventpoll hack: the io_uring FDs stay open, the existing
`eventpoll.c` filter drops their epoll TFDs (it `readlink`s them while open), and
the drain simply expects the right count.

## Result

OpenFold3 (previously instant `-22`) dumped **11GB, zero failures**, past the
blocker. Same binary applies to Boltz2 and MSA-Search. Built binary staged at
`s3://mlspec-archvteams-2407-ckpt/criu-tools/criu-patched-v9-iouring`.

## Apply / rebuild

```
python3 apply_iouring_drain_fix.py          # edits criu-src in place
cd /opt/criu/criu-src && make -j$(nproc)
cp criu/criu /opt/criu/criu-patched          # deploy
```
Base: CRIU 4.2 + the Phase-5/6 patch set (cuda_plugin, io_uring parasite skip,
eventpoll io_uring filter). This fix completes the io_uring path.
