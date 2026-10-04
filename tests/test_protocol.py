"""Hypothesis checks for malformed TCP frames and defensive RPC paths."""

import json
import socket
from tempfile import TemporaryDirectory
from threading import Thread

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.rpc import MAX_BODY, RpcClient, RpcServer, start_background_server


def _request(port, size, code, body=b"", truncate=False):
    """Send one raw request and decode its response if one is sent."""
    frame = size.to_bytes(5, "big") + code.to_bytes(2, "big") + body
    with socket.create_connection(("127.0.0.1", port)) as connection:
        connection.sendall(frame[:3] if truncate else frame)
        connection.shutdown(socket.SHUT_WR)
        header = _receive(connection, 5)
        if not header:
            return None
        length = int.from_bytes(header[1:], "big")
        return header[0], json.loads(_receive(connection, length))


def _receive(connection, count):
    """Read a complete test frame or detect a closed connection."""
    chunks = bytearray()
    while len(chunks) < count:
        part = connection.recv(count - len(chunks))
        if not part:
            return None
        chunks.extend(part)
    return bytes(chunks)


def _serve_one_reply(frame):
    """Start a deliberately faulty one-shot TCP peer."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def serve():
        with listener:
            connection, _ = listener.accept()
            with connection:
                connection.recv(4096)
                connection.sendall(frame)

    thread = Thread(target=serve, daemon=True)
    thread.start()
    return port, thread


@settings(max_examples=3, deadline=None)
@given(st.integers(min_value=11, max_value=65000))
def test_reject_malformed_requests(unknown_code):
    """Reject malformed frames and keep response journaling intact."""
    with TemporaryDirectory() as directory:
        server, thread = start_background_server(
            journal_path=f"{directory}/journal.log"
        )
        port = server.server_address[1]
        try:
            for size, code, body, message in (
                (MAX_BODY + 1, 1, b"", "too large"),
                (2, 1, b"[]", "JSON object"),
                (2, unknown_code, b"{}", "unknown operation"),
                (1, 1, b"[", "Expecting value"),
                (1, 1, b"\xff", "decode"),
            ):
                response_code, payload = _request(port, size, code, body)
                assert response_code == 0
                assert not payload["ok"]
                assert message in payload["error"]
            assert _request(port, 0, 1, truncate=True) is None
            with pytest.raises(OSError):
                RpcServer(
                    server.server_address,
                    journal_path=f"{directory}/failed.log",
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        with open(f"{directory}/journal.log", encoding="utf-8") as log:
            assert len(log.readlines()) == 5


@settings(max_examples=3, deadline=None)
@given(st.text(max_size=8))
def test_reject_invalid_responses(value):
    """Client validates length, operation and completeness of replies."""
    payload = json.dumps({"ok": True, "result": [value]}).encode()
    frames = (
        (
            bytes([2]) + (MAX_BODY + 1).to_bytes(4, "big"),
            ValueError,
            "too large",
        ),
        (
            bytes([3]) + len(payload).to_bytes(4, "big") + payload,
            ValueError,
            "unexpected response operation",
        ),
        (
            bytes([2]) + len(payload).to_bytes(4, "big") + payload[:2],
            ConnectionError,
            "connection closed",
        ),
    )
    for frame, error_type, message in frames:
        port, thread = _serve_one_reply(frame)
        with pytest.raises(error_type, match=message):
            RpcClient(port=port).get_people()
        thread.join()
    with pytest.raises(ValueError, match="too large"):
        RpcClient().create_person({"locale": "x" * (MAX_BODY + 1)})
