"""
McpClient – JSON-RPC 2.0 client for the MCP stdio transport.

Handles the protocol layer over a subprocess's stdin/stdout:

* ``initialize`` handshake
* ``tools/list`` discovery
* ``tools/call`` execution

Stdout is exclusively used for JSON-RPC messages.
Stderr is left for the caller to consume as log output.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any

_log = logging.getLogger(__name__)


class McpClient:
    """Low-level MCP JSON-RPC 2.0 client over stdin/stdout.

    Parameters
    ----------
    proc:
        A ``subprocess.Popen`` instance whose *stdout* carries protocol
        messages and *stdin* accepts requests.  Must be opened in text
        mode (``text=True``).
    name:
        Human-readable server name, used only for logging.
    """

    def __init__(self, proc, name: str = "") -> None:
        self._proc = proc
        self._name = name
        self._next_id = 0
        self._lock = threading.Lock()
        self._pending: dict[int, threading.Event] = {}
        self._results: dict[int, dict] = {}
        self._closed = False

        self._reader = threading.Thread(
            target=self._read_stdout, daemon=True,
            name=f"mcp-proto-{name}",
        )
        self._reader.start()

    # ------------------------------------------------------------------
    # Stdout reader (protocol messages)
    # ------------------------------------------------------------------

    def _read_stdout(self) -> None:
        """Read JSON-RPC messages from the server's stdout."""
        try:
            assert self._proc.stdout is not None
            for raw_line in self._proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    _log.debug("[MCP:%s] non-JSON stdout: %s", self._name, line[:200])
                    continue

                msg_id = msg.get("id")
                if msg_id is not None:
                    with self._lock:
                        ev = self._pending.pop(msg_id, None)
                    if ev:
                        self._results[msg_id] = msg
                        ev.set()
                    else:
                        _log.debug("[MCP:%s] unmatched response id=%s", self._name, msg_id)
                # else: notification — ignore for now
        except Exception:
            _log.debug("[MCP:%s] stdout reader ended", self._name, exc_info=True)
        finally:
            self._closed = True
            # Wake all pending callers so they don't hang forever
            with self._lock:
                for ev in self._pending.values():
                    ev.set()
                self._pending.clear()

    # ------------------------------------------------------------------
    # Request / notification helpers
    # ------------------------------------------------------------------

    def _request(self, method: str, params: dict | None = None,
                 timeout: float = 30) -> dict:
        """Send a JSON-RPC request and wait for the response."""
        if self._closed:
            raise RuntimeError(f"MCP connection to '{self._name}' is closed")

        with self._lock:
            self._next_id += 1
            req_id = self._next_id
            ev = threading.Event()
            self._pending[req_id] = ev

        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params

        try:
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            with self._lock:
                self._pending.pop(req_id, None)
            raise RuntimeError(f"MCP write failed for '{self._name}': {exc}") from exc

        if not ev.wait(timeout):
            with self._lock:
                self._pending.pop(req_id, None)
            raise TimeoutError(
                f"MCP {method} to '{self._name}' timed out after {timeout}s"
            )

        result = self._results.pop(req_id, None)
        if result is None:
            raise RuntimeError(
                f"MCP {method}: no response from '{self._name}' (connection closed?)"
            )

        if "error" in result:
            err = result["error"]
            raise RuntimeError(
                f"MCP {method} error from '{self._name}': "
                f"{err.get('message', err)}"
            )

        return result.get("result", {})

    def _notify(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        try:
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()
        except (OSError, BrokenPipeError):
            _log.debug("[MCP:%s] notify %s failed (pipe closed)", self._name, method)

    # ------------------------------------------------------------------
    # MCP protocol methods
    # ------------------------------------------------------------------

    def initialize(self, timeout: float = 30) -> dict:
        """Perform the MCP initialize handshake.

        Returns the server's capabilities dict.
        """
        result = self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "RepoCode", "version": "1.0.0"},
        }, timeout=timeout)
        self._notify("notifications/initialized")
        _log.info("[MCP:%s] initialized – server: %s",
                  self._name, result.get("serverInfo", {}))
        return result

    def list_tools(self, timeout: float = 15) -> list[dict]:
        """Return the list of tools the server exposes.

        Each tool dict has ``name``, ``description``, ``inputSchema``.
        """
        result = self._request("tools/list", timeout=timeout)
        tools = result.get("tools", [])
        _log.info("[MCP:%s] discovered %d tool(s)", self._name, len(tools))
        return tools

    def call_tool(self, name: str, arguments: dict,
                  timeout: float = 120) -> str:
        """Call a tool and return the text result.

        Extracts text content from the MCP response; falls back to a
        JSON dump of the raw content array.
        """
        result = self._request("tools/call", {
            "name": name,
            "arguments": arguments,
        }, timeout=timeout)

        is_error = result.get("isError", False)
        content = result.get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        text = "\n".join(texts) if texts else json.dumps(content)

        if is_error:
            return f"MCP tool error: {text}"
        return text

    @property
    def is_closed(self) -> bool:
        return self._closed
