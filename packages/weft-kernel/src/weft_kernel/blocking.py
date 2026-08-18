"""The categorical blocking-call detector — fitness function 7(b).

Specified in `docs/01-high-level-plan.md` → *Fitness functions*, clause 7(b),
and `docs/02-extension-model.md` → *Colour*: while a stage runs, a detector
installed at the registration seam fails the build on a blocking call made on
the event loop thread — file IO, sockets, `time.sleep`, `subprocess`, and (for
free, because most of them go through a socket to do it) a synchronous
database driver. **Categorical, not a threshold.** The rejected alternative
was a slow-callback duration constant; it was rejected because its correct
value is machine-dependent and changes legitimately with every runner and
dependency bump, so it cannot be ratcheted the way the kernel budget can.
There is nothing to tune here: a call either happened on the loop thread
during a stage's `run`, or it did not.

**Detecting the operation, not the object.** A `socket.socket()` call
constructs an object; it does not block. What blocks is a *use* of that
object in blocking mode — `connect`, `recv`, `recv_into`, `send`, `sendall`
or `accept` called on a socket whose timeout is not `0`. `asyncio`'s own
`BaseEventLoop._connect_sock` builds every outbound connection's socket via
this same constructor and then immediately calls `sock.setblocking(False)`
(equivalent to `settimeout(0)`) before touching it — so a detector that
fired on construction would flag every legitimate async HTTP call, embedding
call and vector-store round trip a stage makes, which is exactly the
traffic `01`'s *Colour* section describes as "invisible to it by
construction". Checking the socket's own `gettimeout()` at the moment of the
operation keeps the detector categorical rather than reintroducing a
threshold: a socket is either in blocking mode or it is not, and Python
already tracks which.

The same six operations, plus `accept`, are patched a second time on
`ssl.SSLSocket`. `ssl.SSLSocket` overrides `connect`, `recv`, `recv_into`,
`send`, `sendall` and `accept` rather than inheriting `socket.socket`'s —
its read/write path runs through the TLS layer (`self._sslobj`), not the
plain-socket implementation the patches above replace — so a synchronous
HTTPS client (`requests`, a sync `httpx.Client`, most sync vendor SDKs)
would otherwise be caught only at `connect` (which does route through
`socket.socket.connect`) and never at the read or write that actually
stalls the loop. `ssl` is imported lazily, inside `_install`, so the kernel
does not pay the interpreter's TLS/OpenSSL binding cost at import time for
a stage that never makes a network call.

The same distinction holds for `subprocess`. `subprocess.Popen(...)`
constructs an object; it does not block — it forks/execs and returns. What
blocks is a *use* of that object: `Popen.wait()` or `Popen.communicate()`.
`asyncio`'s own `_UnixSubprocessTransport._start` (the machinery behind
`await asyncio.create_subprocess_exec(...)`, the only correct way to run a
subprocess from async code) builds the child via this same constructor on
the event loop thread — so a detector that fired on construction would
raise inside every correct, awaited subprocess call a stage makes. Patching
`wait`/`communicate` instead loses no real detection: `subprocess.run`,
`check_output` and `check_call` all route through `communicate` then `wait`,
so every synchronous convenience wrapper is still caught unconditionally —
there is no timeout or blocking-mode flag to check first, because these two
calls block by definition. `asyncio.subprocess.Process.wait` goes through
the transport and its child watcher, never through `Popen.wait`, so the
awaited path never reaches the patch.

**Scope, and why it does not false-positive on the sanctioned escape hatch.**
`guard()` arms a `ContextVar` for the duration of one stage's `run` call,
recording the stage's label and the identifier of the thread running the
event loop at that moment. Several stdlib entry points are patched, once, to
consult it:

- `ContextVar` is copied per `asyncio.Task`, never shared, so a *second*,
  unrelated pipeline running concurrently on the same loop carries its own
  (unarmed) copy and is untouched — this is what "scoped to stage execution"
  means at run time, not merely at the source level.
- `asyncio.to_thread` propagates the current `Context` into its worker thread
  by design, so the var *is* still armed there — but the thread id captured
  at `guard()`'s entry no longer matches `threading.get_ident()` inside the
  worker, so a call a stage deliberately offloaded is not flagged. That is
  the sanctioned way to make a blocking call, per `01` → *Colour*, and it is
  excluded by construction rather than by an author remembering to mark it.
- Fixtures, imports and model downloads run before `guard()` is entered or
  after it exits, so they were never in scope to begin with — `01` states
  this as a design property of the seam, not a claim this module has to
  enforce.

**What this does not, and must not, become.** `docs/02-extension-model.md`
names the trap directly: this detector sees only *blocking* calls on the loop
thread. An async HTTP client, or anything already behind `to_thread`, is
invisible to it by construction — sound for colour, unsound for security. It
must never be reused as a network- or filesystem-access observer.
"""

from __future__ import annotations

import builtins
import io
import socket
import subprocess
import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from weft_kernel.errors import WeftError

if TYPE_CHECKING:
    import ssl


class BlockingCallError(WeftError):
    """A stage made a blocking call on the event loop thread. Fitness function 7(b).

    Raised from inside the blocking call itself — `open`, a socket operation,
    `time.sleep`, or `Popen.wait`/`Popen.communicate` — so the traceback
    points at the exact call site, not merely at the stage that eventually
    made it.
    """


@dataclass(frozen=True, slots=True)
class _Watch:
    """What one armed `guard()` window remembers, for the patched functions to consult."""

    stage: str
    loop_thread_id: int


_watch: ContextVar[_Watch | None] = ContextVar("weft_kernel_blocking_watch", default=None)

_installed = False

_real_open: Callable[..., Any] = builtins.open
_real_io_open: Callable[..., Any] = io.open
_real_sleep: Callable[..., None] = time.sleep
_real_popen_wait: Callable[..., int] = subprocess.Popen[Any].wait
_real_popen_communicate: Callable[..., tuple[Any, Any]] = subprocess.Popen[Any].communicate
_real_socket_connect: Callable[..., Any] = socket.socket.connect
_real_socket_recv: Callable[..., Any] = socket.socket.recv
_real_socket_recv_into: Callable[..., Any] = socket.socket.recv_into
_real_socket_send: Callable[..., Any] = socket.socket.send
_real_socket_sendall: Callable[..., Any] = socket.socket.sendall
_real_socket_accept: Callable[..., Any] = socket.socket.accept


def _ssl_patch_not_installed(*_args: Any, **_kwargs: Any) -> Any:
    msg = "ssl.SSLSocket patch not installed"
    raise RuntimeError(msg)


_real_ssl_socket_connect: Callable[..., Any] = _ssl_patch_not_installed
_real_ssl_socket_recv: Callable[..., Any] = _ssl_patch_not_installed
_real_ssl_socket_recv_into: Callable[..., Any] = _ssl_patch_not_installed
_real_ssl_socket_send: Callable[..., Any] = _ssl_patch_not_installed
_real_ssl_socket_sendall: Callable[..., Any] = _ssl_patch_not_installed
_real_ssl_socket_accept: Callable[..., Any] = _ssl_patch_not_installed


@contextmanager
def guard(stage: str) -> Generator[None]:
    """Scope the detector to `stage`'s execution, for the lifetime of this `with` block.

    Installs the stdlib patches on first use (idempotent — a second `guard()`
    call, nested or sequential, does not re-patch), then arms the watch for
    this task on this thread. Reset on the way out, including on an
    exception: `guard` never decides whether a stage failed, it only decides
    whether a call it made was blocking.
    """
    _install()
    token = _watch.set(_Watch(stage=stage, loop_thread_id=threading.get_ident()))
    try:
        yield
    finally:
        _watch.reset(token)


def _install() -> None:
    """Patch the stdlib's blocking entry points, once per process.

    `builtins.open` and `io.open` are patched separately because they are
    distinct callables — `pathlib.Path.read_text`/`read_bytes` route through
    `io.open`, not `builtins.open`, and this repository's own ruff `PTH`
    rules push authors toward `Path`, so the file-IO clause of 7(b) would be
    inert for the idiom this codebase mandates if only `builtins.open` were
    covered.

    The socket entry points are the six *operations* that can block —
    `connect`, `recv`, `recv_into`, `send`, `sendall`, `accept` — patched as
    bound methods on `socket.socket` itself, not by substituting the class.
    Substituting the class would make `isinstance(x, socket.socket)` false
    for objects built through the real constructor, which `asyncio` and
    `ssl` both rely on; patching methods in place leaves class identity, and
    therefore `isinstance`, untouched.

    The subprocess entry points are, by the same reasoning, the two
    *operations* that can block — `Popen.wait`, `Popen.communicate` — not
    `Popen.__init__`. Construction only forks/execs; `await
    asyncio.create_subprocess_exec(...)` calls it on the event loop thread by
    design (`_UnixSubprocessTransport._start`), so patching the constructor
    would flag every correct, awaited subprocess call a stage makes. `wait`
    and `communicate` block unconditionally when called synchronously — there
    is no non-blocking mode to check for a `Popen`, unlike a socket's
    `gettimeout()` — so both patches call `_check` on every invocation while
    armed.

    `ssl` is imported here, lazily, and its `SSLSocket` gets the same six
    operations patched a second time — `connect`, `recv`, `recv_into`,
    `send`, `sendall`, `accept` — because `SSLSocket` overrides all six
    rather than inheriting `socket.socket`'s, so the patches above never see
    a TLS socket's read or write. Guarded by the same `gettimeout() != 0`
    check: a non-blocking TLS socket is exactly as exempt as a non-blocking
    plain one.

    Every patch is a pass-through outside an armed `guard()` window, and for
    a socket, also a pass-through whenever the socket is not in blocking mode
    (`gettimeout() == 0`) — nothing about their behaviour changes for code
    that never runs as a stage, or for a socket already opted into async use.
    This is what makes eager, process-wide installation safe: the gate this
    function installs defaults to open.
    """
    global _installed
    global _real_ssl_socket_connect, _real_ssl_socket_recv, _real_ssl_socket_recv_into
    global _real_ssl_socket_send, _real_ssl_socket_sendall, _real_ssl_socket_accept
    if _installed:
        return
    builtins.open = _guarded_open
    io.open = _guarded_io_open
    time.sleep = _guarded_sleep
    subprocess.Popen.wait = _guarded_popen_wait
    subprocess.Popen.communicate = _guarded_popen_communicate
    socket.socket.connect = _guarded_socket_connect
    socket.socket.recv = _guarded_socket_recv
    socket.socket.recv_into = _guarded_socket_recv_into
    socket.socket.send = _guarded_socket_send
    socket.socket.sendall = _guarded_socket_sendall
    socket.socket.accept = _guarded_socket_accept

    import ssl

    _real_ssl_socket_connect = ssl.SSLSocket.connect
    _real_ssl_socket_recv = ssl.SSLSocket.recv
    _real_ssl_socket_recv_into = ssl.SSLSocket.recv_into
    _real_ssl_socket_send = ssl.SSLSocket.send
    _real_ssl_socket_sendall = ssl.SSLSocket.sendall
    _real_ssl_socket_accept = ssl.SSLSocket.accept
    ssl.SSLSocket.connect = _guarded_ssl_socket_connect
    ssl.SSLSocket.recv = _guarded_ssl_socket_recv
    ssl.SSLSocket.recv_into = _guarded_ssl_socket_recv_into
    ssl.SSLSocket.send = _guarded_ssl_socket_send
    ssl.SSLSocket.sendall = _guarded_ssl_socket_sendall
    ssl.SSLSocket.accept = _guarded_ssl_socket_accept

    _installed = True


def _check(call: str) -> None:
    watch = _watch.get()
    if watch is None or watch.loop_thread_id != threading.get_ident():
        return
    raise BlockingCallError(
        f"stage '{watch.stage}' made a blocking call ({call}) on the event loop thread. "
        f"Offload it — `await asyncio.to_thread(...)` — or use an async client instead. "
        f"See fitness function 7(b), docs/01-high-level-plan.md.",
        stage=watch.stage,
    )


def _guarded_open(*args: Any, **kwargs: Any) -> Any:
    _check("open()")
    return _real_open(*args, **kwargs)


def _guarded_io_open(*args: Any, **kwargs: Any) -> Any:
    _check("open()")
    return _real_io_open(*args, **kwargs)


def _guarded_sleep(*args: Any, **kwargs: Any) -> None:
    _check("time.sleep()")
    _real_sleep(*args, **kwargs)


def _guarded_popen_wait(self: subprocess.Popen[Any], *args: Any, **kwargs: Any) -> int:
    _check("subprocess.wait()")
    return _real_popen_wait(self, *args, **kwargs)


def _guarded_popen_communicate(
    self: subprocess.Popen[Any], *args: Any, **kwargs: Any
) -> tuple[Any, Any]:
    _check("subprocess.communicate()")
    return _real_popen_communicate(self, *args, **kwargs)


def _is_blocking(sock: socket.socket) -> bool:
    """A socket is in blocking mode unless it opted out with `settimeout(0)`.

    `gettimeout()` returns `None` for the default blocking mode and a
    `float` timeout for both the "blocking with a deadline" and the
    non-blocking (`0`) modes — so the only value that means "this socket
    will not block the loop thread" is exactly `0`.
    """
    return sock.gettimeout() != 0


def _guarded_socket_connect(self: socket.socket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("socket.connect()")
    return _real_socket_connect(self, *args, **kwargs)


def _guarded_socket_recv(self: socket.socket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("socket.recv()")
    return _real_socket_recv(self, *args, **kwargs)


def _guarded_socket_recv_into(self: socket.socket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("socket.recv_into()")
    return _real_socket_recv_into(self, *args, **kwargs)


def _guarded_socket_send(self: socket.socket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("socket.send()")
    return _real_socket_send(self, *args, **kwargs)


def _guarded_socket_sendall(self: socket.socket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("socket.sendall()")
    return _real_socket_sendall(self, *args, **kwargs)


def _guarded_socket_accept(self: socket.socket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("socket.accept()")
    return _real_socket_accept(self, *args, **kwargs)


def _guarded_ssl_socket_connect(self: ssl.SSLSocket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("ssl.SSLSocket.connect()")
    return _real_ssl_socket_connect(self, *args, **kwargs)


def _guarded_ssl_socket_recv(self: ssl.SSLSocket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("ssl.SSLSocket.recv()")
    return _real_ssl_socket_recv(self, *args, **kwargs)


def _guarded_ssl_socket_recv_into(self: ssl.SSLSocket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("ssl.SSLSocket.recv_into()")
    return _real_ssl_socket_recv_into(self, *args, **kwargs)


def _guarded_ssl_socket_send(self: ssl.SSLSocket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("ssl.SSLSocket.send()")
    return _real_ssl_socket_send(self, *args, **kwargs)


def _guarded_ssl_socket_sendall(self: ssl.SSLSocket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("ssl.SSLSocket.sendall()")
    return _real_ssl_socket_sendall(self, *args, **kwargs)


def _guarded_ssl_socket_accept(self: ssl.SSLSocket, *args: Any, **kwargs: Any) -> Any:
    if _is_blocking(self):
        _check("ssl.SSLSocket.accept()")
    return _real_ssl_socket_accept(self, *args, **kwargs)
