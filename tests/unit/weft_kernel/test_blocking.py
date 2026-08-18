"""Unit tests for `weft_kernel.blocking`.

Mirrors `packages/weft-kernel/src/weft_kernel/blocking.py`. Covers the gate
defaulting to open outside an armed `guard()` (both during ordinary work
inside a guard, and for real after the guard has exited), the sanctioned
`asyncio.to_thread` and non-blocking-socket escape hatches, the patched
entry points refusing a blocking call made on the loop thread, and the
`_install` idempotence branch a nested or repeated `guard()` call exercises.
"""

import asyncio
import builtins
import socket
import ssl
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from weft_kernel import blocking
from weft_kernel.blocking import BlockingCallError, guard


async def test_ordinary_work_inside_guard_is_unaffected() -> None:
    # Arrange / Act
    with guard("weft-example:demo"):
        result = 2 + 2

    # Assert
    assert result == 4


async def test_a_call_offloaded_via_to_thread_is_not_flagged() -> None:
    # Arrange / Act
    with guard("weft-example:demo"):
        slept = await asyncio.to_thread(time.sleep, 0)

    # Assert
    assert slept is None


async def test_asyncio_open_connection_inside_guard_is_not_flagged() -> None:
    # Arrange — a plain listening socket, not `asyncio.start_server`: its
    # `Server.wait_closed()` has an unrelated hang on some 3.12 patch
    # releases that this test must not depend on.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    host, port = listener.getsockname()

    try:
        # Act
        with guard("weft-example:demo"):
            _reader, writer = await asyncio.open_connection(host, port)

        # Assert
        writer.close()
        await writer.wait_closed()
    finally:
        listener.close()


async def test_a_blocking_call_on_a_tls_socket_is_refused() -> None:
    # Arrange — an unhandshaked TLS socket is enough: the guard checks
    # `gettimeout()` before touching the real `recv`, so no live peer is
    # needed to prove the patch, only that `ssl.SSLSocket.recv` (which
    # overrides `socket.socket.recv` rather than inheriting it) is reached.
    raw, peer = socket.socketpair()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    tls_socket = context.wrap_socket(raw, server_hostname=None, do_handshake_on_connect=False)

    try:
        # Act / Assert
        with pytest.raises(BlockingCallError) as excinfo, guard("weft-example:demo"):
            tls_socket.recv(1)

        assert "weft-example:demo" in str(excinfo.value)
    finally:
        tls_socket.close()
        peer.close()


async def test_asyncio_create_subprocess_exec_inside_guard_is_not_flagged() -> None:
    # Arrange / Act
    with guard("weft-example:demo"):
        proc = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass")
        returncode = await proc.wait()

    # Assert
    assert returncode == 0


@pytest.mark.parametrize(
    "make_blocking_call",
    [
        pytest.param(
            lambda: open("/nonexistent/weft-probe", encoding="utf-8"),  # noqa: PTH123, SIM115
            id="open",
        ),
        pytest.param(lambda: Path("/nonexistent/weft-probe").read_text(), id="path-read-text"),
        pytest.param(lambda: socket.socket().connect(("127.0.0.1", 1)), id="socket-connect"),
        pytest.param(lambda: time.sleep(0), id="sleep"),
        pytest.param(
            lambda: subprocess.run(  # noqa: S603
                [sys.executable, "-c", "pass"], check=False
            ),
            id="subprocess-run-via-communicate-and-wait",
        ),
    ],
)
async def test_a_blocking_call_on_the_loop_thread_is_refused(
    make_blocking_call: Callable[[], object],
) -> None:
    # Arrange / Act / Assert
    with pytest.raises(BlockingCallError) as excinfo, guard("weft-example:demo"):
        make_blocking_call()

    assert "weft-example:demo" in str(excinfo.value)


async def test_the_gate_defaults_to_open_after_a_guard_has_exited(tmp_path: Path) -> None:
    # Arrange
    probe = tmp_path / "weft-probe.txt"
    probe.write_text("weft", encoding="utf-8")
    with guard("weft-example:demo"):
        pass

    # Act
    read_via_path = probe.read_text(encoding="utf-8")
    with open(probe, encoding="utf-8") as handle:  # noqa: PTH123
        read_via_open = handle.read()
    sock = socket.socket()
    sock.close()
    time.sleep(0)
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "pass"], check=False
    )

    # Assert
    assert (read_via_path, read_via_open, completed.returncode) == ("weft", "weft", 0)


def test_guard_does_not_repatch_when_already_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setattr(blocking, "_installed", True)
    sentinel = object()
    monkeypatch.setattr(builtins, "open", sentinel)

    # Act
    with guard("weft-example:demo"):
        pass

    # Assert
    assert builtins.open is sentinel
