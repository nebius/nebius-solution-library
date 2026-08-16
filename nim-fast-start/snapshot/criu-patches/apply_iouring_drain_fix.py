import re

# 1) parasite-syscall.c: rewrite the drain function to compute expected count via readlink
f = "/opt/criu/criu-src/criu/parasite-syscall.c"
s = open(f).read()
start = s.index("int parasite_drain_fds_seized(")
depth = 0
i = s.index("{", start)
j = i
while j < len(s):
    if s[j] == "{":
        depth += 1
    elif s[j] == "}":
        depth -= 1
        if depth == 0:
            break
    j += 1
old_fn = s[start:j + 1]

new_fn = r'''int parasite_drain_fds_seized(struct parasite_ctl *ctl, struct parasite_drain_fd *dfds, int nr_fds, int off, int *lfds,
			      struct fd_opts *opts, pid_t victim_pid)
{
	int ret = -1, size, sk, i, j, expected;
	struct parasite_drain_fd *args;
	int *kept = NULL, *tmp_lfds = NULL;
	struct fd_opts *tmp_opts = NULL;

	size = drain_fds_size(dfds);
	args = compel_parasite_args_s(ctl, size);
	args->nr_fds = nr_fds;
	memcpy(&args->fds, dfds->fds + off, sizeof(int) * nr_fds);

	ret = compel_rpc_call(PARASITE_CMD_DRAIN_FDS, ctl);
	if (ret) {
		pr_err("Parasite failed to drain descriptors\n");
		goto err;
	}

	sk = compel_rpc_sock(ctl);

	/*
	 * The parasite skips io_uring FDs (kernel 6.x blocks SCM_RIGHTS for
	 * anon_inode:[io_uring]) and sends only the remaining FDs, in original
	 * order. Its write-back of the reduced count is NOT visible here (the
	 * parasite runs on an injected copy of args), so we independently
	 * determine which FDs it kept by readlink() and expect exactly that many.
	 */
	for (i = 0; i < nr_fds; i++) {
		lfds[i] = -1;
		memset(opts + i, 0, sizeof(struct fd_opts));
	}

	kept = xmalloc(nr_fds * sizeof(int));
	if (!kept) {
		ret = -1;
		goto err;
	}
	expected = 0;
	for (i = 0; i < nr_fds; i++) {
		char _lp[64], _lt[64];
		ssize_t _l;
		snprintf(_lp, sizeof(_lp), "/proc/%d/fd/%d", victim_pid, dfds->fds[off + i]);
		_l = readlink(_lp, _lt, sizeof(_lt) - 1);
		if (_l > 0)
			_lt[_l] = 0;
		if (_l > 0 && strstr(_lt, "[io_uring]")) {
			pr_info("drain: skipping io_uring fd %d (matches parasite)\n", dfds->fds[off + i]);
			continue;
		}
		kept[expected++] = i;
	}

	if (expected > 0) {
		tmp_lfds = xmalloc(expected * sizeof(int));
		tmp_opts = xmalloc(expected * sizeof(struct fd_opts));
		if (!tmp_lfds || !tmp_opts) {
			ret = -1;
			goto err;
		}
		ret = recv_fds(sk, tmp_lfds, expected, tmp_opts, sizeof(struct fd_opts));
		if (ret) {
			pr_err("Can't retrieve FDs from socket\n");
			goto err;
		}
		for (j = 0; j < expected; j++) {
			lfds[kept[j]] = tmp_lfds[j];
			opts[kept[j]] = tmp_opts[j];
		}
	} else {
		ret = 0;
	}

	ret |= compel_rpc_sync(PARASITE_CMD_DRAIN_FDS, ctl);
err:
	if (kept)
		xfree(kept);
	if (tmp_lfds)
		xfree(tmp_lfds);
	if (tmp_opts)
		xfree(tmp_opts);
	return ret;
}'''

assert old_fn in s
s = s.replace(old_fn, new_fn)
open(f, "w").write(s)
print("parasite-syscall.c: drain rewritten (readlink-based count)")

# 2) prototype in parasite-syscall.h
h = "/opt/criu/criu-src/criu/include/parasite-syscall.h"
hs = open(h).read()
m = re.search(r"parasite_drain_fds_seized\(.*?struct fd_opts \*opts\)", hs, flags=re.S)
if m and "victim_pid" not in m.group(0):
    hs = hs.replace(m.group(0), m.group(0)[:-1] + ", pid_t victim_pid)")
    open(h, "w").write(hs)
    print("header updated")
else:
    print("header: already updated or pattern not found ->", bool(m))

# 3) caller in files.c
c = "/opt/criu/criu-src/criu/files.c"
cs = open(c).read()
old_call = "parasite_drain_fds_seized(ctl, dfds, nr_fds, off, lfds, opts)"
new_call = "parasite_drain_fds_seized(ctl, dfds, nr_fds, off, lfds, opts, item->pid->real)"
if old_call in cs:
    cs = cs.replace(old_call, new_call)
    open(c, "w").write(cs)
    print("files.c caller updated")
else:
    print("files.c: caller pattern not found (maybe already patched)")
