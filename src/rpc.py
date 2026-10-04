"""Length-prefixed JSON RPC over TCP for the data model."""

import json
import logging
import socket
import socketserver
from threading import Thread

from .model import DataModel, OPERATIONS


MAX_BODY = 1_000_000
REQUEST_HEADER = 7
RESPONSE_HEADER = 5


def _read_exact(stream, count):
    data = bytearray()
    while len(data) < count:
        part = stream.recv(count - len(data))
        if not part:
            raise ConnectionError("connection closed during frame")
        data.extend(part)
    return bytes(data)


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _pack_response(code, payload):
    body = _json_bytes(payload)
    return bytes([code]) + len(body).to_bytes(4, "big") + body


class RpcHandler(socketserver.BaseRequestHandler):
    """Serve multiple requests on each TCP connection."""

    def handle(self):
        while True:
            first = self.request.recv(1)
            if not first:
                return
            try:
                header = first + _read_exact(
                    self.request, REQUEST_HEADER - 1
                )
                size = int.from_bytes(header[:5], "big")
                code = int.from_bytes(header[5:], "big")
                if size > MAX_BODY:
                    raise ValueError("request body is too large")
                body = _read_exact(self.request, size)
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                if not 1 <= code <= len(OPERATIONS):
                    raise ValueError("unknown operation")
                method = getattr(self.server.model, OPERATIONS[code - 1])
                result = method(**payload)
                response = {"ok": True, "result": result}
            except (ValueError, TypeError, KeyError, json.JSONDecodeError,
                    ConnectionError) as error:
                response = {"ok": False, "error": str(error)}
                if isinstance(error, ConnectionError):
                    return
                code = 0
            frame = _pack_response(code, response)
            self.server.journal.info(frame.hex())
            self.request.sendall(frame)


class RpcServer(socketserver.ThreadingTCPServer):
    """Threaded server sharing one protected in-memory model."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, model=None, journal_path="journal.log"):
        self.model = model or DataModel()
        self.journal = logging.getLogger(f"rpc.{id(self)}")
        self.journal.setLevel(logging.INFO)
        self.journal.propagate = False
        handler = logging.FileHandler(journal_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.journal.addHandler(handler)
        try:
            super().__init__(address, RpcHandler)
        except Exception:
            handler.close()
            self.journal.removeHandler(handler)
            raise

    def server_close(self):
        super().server_close()
        for handler in self.journal.handlers[:]:
            handler.close()
            self.journal.removeHandler(handler)


def start_background_server(address=("127.0.0.1", 0),
                            journal_path="journal.log"):
    """Start a server for demonstrations and tests."""
    server = RpcServer(address, journal_path=journal_path)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


class RpcClient:
    """Client with the same ten public method names as DataModel."""

    def __init__(self, host="127.0.0.1", port=8765, timeout=5):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _call(self, name, payload):
        code = OPERATIONS.index(name) + 1
        body = _json_bytes(payload)
        if len(body) > MAX_BODY:
            raise ValueError("request body is too large")
        frame = len(body).to_bytes(5, "big")
        frame += code.to_bytes(2, "big") + body
        with socket.create_connection(
            (self.host, self.port), timeout=self.timeout
        ) as connection:
            connection.sendall(frame)
            header = _read_exact(connection, RESPONSE_HEADER)
            length = int.from_bytes(header[1:], "big")
            if length > MAX_BODY:
                raise ValueError("response body is too large")
            response = json.loads(_read_exact(connection, length))
        if not response["ok"]:
            raise ValueError(response["error"])
        if header[0] != code:
            raise ValueError("unexpected response operation")
        return response["result"]

    def create_person(self, record):
        """Create a Person remotely."""
        return self._call("create_person", {"record": record})

    def get_people(self):
        """List Person records remotely."""
        return self._call("get_people", {})

    def edit_person(self, identifier, changes):
        """Edit a Person remotely."""
        return self._call("edit_person", {
            "identifier": identifier, "changes": changes
        })

    def create_query(self, record):
        """Create a Query remotely."""
        return self._call("create_query", {"record": record})

    def get_queries(self):
        """List Query records remotely."""
        return self._call("get_queries", {})

    def edit_query(self, identifier, changes):
        """Edit a Query remotely."""
        return self._call("edit_query", {
            "identifier": identifier, "changes": changes
        })

    def create_result(self, record):
        """Create a Result remotely."""
        return self._call("create_result", {"record": record})

    def get_results(self):
        """List Result records remotely."""
        return self._call("get_results", {})

    def edit_result(self, identifier, changes):
        """Edit a Result remotely."""
        return self._call("edit_result", {
            "identifier": identifier, "changes": changes
        })

    def recent_queries(self, now=None):
        """Return the recent locale/content join remotely."""
        return self._call("recent_queries", {"now": now})
