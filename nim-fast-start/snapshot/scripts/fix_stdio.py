#!/usr/bin/env python3
"""
Redirect a process's stdout (fd 1) and stderr (fd 2) to /dev/null using ptrace.

Required for CRIU-restored processes whose stdout/stderr pipes have no reader.
When CRIU uses --shell-job, the restored process's stdio pipes connect to the
original container's stdout/stderr, which may be closed in the restore context.
Writes to these broken pipes return EPIPE (SIGPIPE is SIG_IGN in Python), which
propagates into inference handlers and causes HTTP 422 errors.

Usage:
  python3 fix_stdio.py <PID>

Requirements: root, CAP_SYS_PTRACE, x86_64 Linux
"""
import ctypes, os, signal, struct, sys

libc = ctypes.cdll.LoadLibrary("libc.so.6")
libc.ptrace.restype = ctypes.c_long
libc.ptrace.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]

PTRACE_ATTACH   = 16
PTRACE_DETACH   = 17
PTRACE_GETREGS  = 12
PTRACE_SETREGS  = 13
PTRACE_PEEKDATA = 2
PTRACE_POKEDATA = 4
PTRACE_CONT     = 7
WUNTRACED       = 2

SYS_open  = 2   # x86_64
SYS_dup2  = 33  # x86_64
SYS_close = 3   # x86_64
O_WRONLY  = 1

class user_regs_struct(ctypes.Structure):
    _fields_ = [
        ("r15", ctypes.c_ulong), ("r14", ctypes.c_ulong),
        ("r13", ctypes.c_ulong), ("r12", ctypes.c_ulong),
        ("rbp", ctypes.c_ulong), ("rbx", ctypes.c_ulong),
        ("r11", ctypes.c_ulong), ("r10", ctypes.c_ulong),
        ("r9",  ctypes.c_ulong), ("r8",  ctypes.c_ulong),
        ("rax", ctypes.c_ulong), ("rcx", ctypes.c_ulong),
        ("rdx", ctypes.c_ulong), ("rsi", ctypes.c_ulong),
        ("rdi", ctypes.c_ulong), ("orig_rax", ctypes.c_ulong),
        ("rip", ctypes.c_ulong), ("cs",  ctypes.c_ulong),
        ("eflags", ctypes.c_ulong), ("rsp", ctypes.c_ulong),
        ("ss",  ctypes.c_ulong), ("fs_base", ctypes.c_ulong),
        ("gs_base", ctypes.c_ulong), ("ds", ctypes.c_ulong),
        ("es",  ctypes.c_ulong), ("fs",  ctypes.c_ulong),
        ("gs",  ctypes.c_ulong),
    ]

def ptrace(request, pid, addr=0, data=0):
    ret = libc.ptrace(request, pid, ctypes.c_void_p(addr), ctypes.c_void_p(data))
    if ret == -1:
        err = ctypes.get_errno()
        if err:
            raise OSError(err, os.strerror(err), f"ptrace({request})")
    return ret

def waitpid(pid):
    status = ctypes.c_int(0)
    ret = libc.waitpid(pid, ctypes.byref(status), WUNTRACED)
    if ret == -1:
        raise OSError(ctypes.get_errno(), "waitpid")
    return status.value

def get_regs(pid):
    regs = user_regs_struct()
    ptrace(PTRACE_GETREGS, pid, 0, ctypes.addressof(regs))
    return regs

def set_regs(pid, regs):
    ptrace(PTRACE_SETREGS, pid, 0, ctypes.addressof(regs))

def peek(pid, addr):
    return ptrace(PTRACE_PEEKDATA, pid, addr, 0)

def poke(pid, addr, val):
    ptrace(PTRACE_POKEDATA, pid, addr, val)

def run_syscall(pid, orig_regs, sysno, *args):
    rip = orig_regs.rip
    orig_word = peek(pid, rip)
    # Inject: syscall (0f 05) + int3 (cc) at current RIP
    injected = (orig_word & ~0xFFFFFF) | 0xcc050f
    poke(pid, rip, injected)

    regs = user_regs_struct()
    ctypes.memmove(ctypes.addressof(regs), ctypes.addressof(orig_regs), ctypes.sizeof(regs))
    regs.rax = sysno
    arg_names = ["rdi", "rsi", "rdx", "r10", "r8", "r9"]
    for i, arg in enumerate(args):
        setattr(regs, arg_names[i], arg & 0xFFFFFFFFFFFFFFFF)
    set_regs(pid, regs)

    ptrace(PTRACE_CONT, pid, 0, 0)
    waitpid(pid)

    ret_regs = get_regs(pid)
    retval = ret_regs.rax
    if retval > (1 << 63):
        retval -= (1 << 64)

    poke(pid, rip, orig_word)
    set_regs(pid, orig_regs)
    return retval

def write_cstr(pid, orig_regs, s):
    addr = (orig_regs.rsp - 256) & ~7
    b = s.encode() + b"\x00"
    while len(b) % 8:
        b += b"\x00"
    for i in range(0, len(b), 8):
        poke(pid, addr + i, struct.unpack("<Q", b[i:i+8])[0])
    return addr

def fix_stdio(pid):
    print(f"Attaching to PID {pid}...")
    ptrace(PTRACE_ATTACH, pid, 0, 0)
    waitpid(pid)
    print("Stopped.")

    try:
        orig = get_regs(pid)
        null_addr = write_cstr(pid, orig, "/dev/null")
        new_fd = run_syscall(pid, orig, SYS_open, null_addr, O_WRONLY, 0)
        if new_fd < 0:
            print(f"open(/dev/null) failed: errno {-new_fd}")
            return

        r1 = run_syscall(pid, orig, SYS_dup2, new_fd, 1)
        r2 = run_syscall(pid, orig, SYS_dup2, new_fd, 2)
        r3 = run_syscall(pid, orig, SYS_close, new_fd)
        print(f"dup2({new_fd}, 1)={r1}  dup2({new_fd}, 2)={r2}  close={r3}")
        print("stdout/stderr redirected to /dev/null.")
    finally:
        ptrace(PTRACE_DETACH, pid, 0, 0)
        print(f"Detached from PID {pid}.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <PID>", file=sys.stderr)
        sys.exit(1)
    fix_stdio(int(sys.argv[1]))
