"""
McpServerRegistry – singleton registry that owns MCP server
configurations **and** their running sub-processes.

Responsibilities
----------------
* Persist server definitions in ``mcp_servers.json`` under the
  application ``base_dir`` (same pattern as ``LLMClientRegistry``).
* Start / stop individual servers or all at once.
* Run the MCP JSON-RPC protocol over each server's **stdout/stdin**;
  capture **stderr** as log output for the debug panel.
* Discover and cache tools from running MCP servers (``tools/list``).
* Execute MCP tool calls on behalf of agent loops (``tools/call``).
* Emit events on the ``EventBus`` for start / stop / output / error.

JSON schema (``mcp_servers.json``)::

    {
        "My Server": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "env": {"NODE_ENV": "production"},
            "enabled": true
        }
    }
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .client import McpClient

_log = logging.getLogger(__name__)

_MCP_SERVERS_FILE = "mcp_servers.json"
_MAX_OUTPUT_LINES = 2000


# ------------------------------------------------------------------
# Data model
# ------------------------------------------------------------------

@dataclass
class McpServerConfig:
    """Serialisable description of *how* to launch one MCP server."""

    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: dict) -> McpServerConfig:
        return cls(
            command=d.get("command", ""),
            args=list(d.get("args", [])),
            env=dict(d.get("env", {})),
            enabled=bool(d.get("enabled", True)),
        )


# ------------------------------------------------------------------
# Per-process bookkeeping
# ------------------------------------------------------------------

class _McpProcess:
    """Wraps a running MCP server subprocess, its protocol client, and
    the stderr log-reader thread."""

    def __init__(self, name: str, proc: subprocess.Popen,
                 client: McpClient,
                 on_output: Callable[[str, str], None],
                 on_exit: Callable[[str, int | None], None]):
        self.name = name
        self.proc = proc
        self.client = client
        self.output: deque[str] = deque(maxlen=_MAX_OUTPUT_LINES)
        self._on_output = on_output
        self._on_exit = on_exit
        # Read stderr for log output (stdout is handled by McpClient)
        self._stderr_reader = threading.Thread(
            target=self._read_stderr, daemon=True, name=f"mcp-stderr-{name}")
        self._stderr_reader.start()

    def _read_stderr(self) -> None:
        """Read stderr lines until the process exits."""
        try:
            assert self.proc.stderr is not None
            for raw_line in self.proc.stderr:
                line = raw_line.rstrip("\n\r")
                self.output.append(line)
                try:
                    self._on_output(self.name, line)
                except Exception:
                    pass
        except Exception:
            _log.debug("MCP stderr reader for %r ended with exception",
                       self.name, exc_info=True)
        finally:
            rc = self.proc.wait()
            try:
                self._on_exit(self.name, rc)
            except Exception:
                pass

    def stop(self) -> None:
        """Terminate the process (gracefully, then forcefully)."""
        if self.proc.poll() is not None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)

    @property
    def is_alive(self) -> bool:
        return self.proc.poll() is None


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------

class McpServerRegistry:
    """Manages MCP server configurations and their running processes.

    Parameters
    ----------
    base_dir:
        Application data directory.  ``mcp_servers.json`` is stored here.
    event_bus:
        Optional EventBus to emit MCP lifecycle events.
    """

    def __init__(self, base_dir: Path | None = None,
                 event_bus: Any | None = None):
        self._configs: dict[str, McpServerConfig] = {}
        self._processes: dict[str, _McpProcess] = {}
        self._output_buffers: dict[str, deque[str]] = {}  # survives process exit
        self._base_dir = base_dir
        self._event_bus = event_bus
        self._lock = threading.Lock()

        # -- MCP tool integration --
        self._tools_cache: dict[str, list[dict]] = {}      # server → raw MCP tool defs
        self._tool_routing: dict[str, tuple[str, str]] = {} # namespaced_name → (server, tool)
        self._ready: dict[str, bool] = {}                   # server → handshake done?

    # ------------------------------------------------------------------
    # JSON persistence
    # ------------------------------------------------------------------

    @property
    def _json_path(self) -> Path | None:
        if self._base_dir is None:
            return None
        return self._base_dir / _MCP_SERVERS_FILE

    def load(self) -> None:
        """Load server configurations from disk."""
        path = self._json_path
        if path is None or not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _log.exception("Failed to read MCP server configs from %s", path)
            return
        for name, cfg_dict in raw.items():
            self._configs[name] = McpServerConfig.from_dict(cfg_dict)

    def _save(self) -> None:
        """Persist current configs to ``mcp_servers.json``."""
        path = self._json_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {n: c.to_dict() for n, c in self._configs.items()}
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            _log.exception("Failed to save MCP server configs to %s", path)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, name: str, config: McpServerConfig) -> None:
        """Add a new server configuration and persist."""
        self._configs[name] = config
        self._save()

    def update(self, name: str, config: McpServerConfig) -> None:
        """Update an existing configuration.  Stops the server if running."""
        was_running = self.is_running(name)
        if was_running:
            self.stop(name)
        self._configs[name] = config
        self._save()
        if was_running and config.enabled:
            self.start(name)

    def unregister(self, name: str) -> None:
        """Remove a server configuration.  Stops the process if running."""
        self.stop(name)
        self._configs.pop(name, None)
        self._save()

    def rename(self, old_name: str, new_name: str) -> None:
        """Rename a server entry."""
        if old_name not in self._configs or new_name in self._configs:
            return
        cfg = self._configs.pop(old_name)
        self._configs[new_name] = cfg
        self._save()

    def get_config(self, name: str) -> McpServerConfig | None:
        return self._configs.get(name)

    def get_config_dict(self, name: str) -> dict | None:
        cfg = self._configs.get(name)
        return cfg.to_dict() if cfg else None

    def all_servers(self) -> dict[str, McpServerConfig]:
        return dict(self._configs)

    def names(self) -> list[str]:
        return list(self._configs.keys())

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------

    def start(self, name: str) -> bool:
        """Start a server by name.  Returns True on success."""
        cfg = self._configs.get(name)
        if cfg is None:
            _log.warning("Cannot start unknown MCP server %r", name)
            return False
        if self.is_running(name):
            _log.info("MCP server %r is already running", name)
            return True

        cmd = [cfg.command, *cfg.args]
        env = {**os.environ, **cfg.env} if cfg.env else None

        # On Windows, use shell=True so cmd.exe resolves .cmd/.bat shims
        # and PATH entries (e.g. npx, node, python).  This matches the
        # behaviour of Claude Desktop and other MCP hosts.
        use_shell = os.name == "nt"

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,   # MCP JSON-RPC protocol
                stderr=subprocess.PIPE,   # server log output
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                shell=use_shell,
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if os.name == "nt" else 0),
            )
        except Exception:
            _log.exception("Failed to start MCP server %r", name)
            self._emit_error(name, "Failed to start process")
            return False

        client = McpClient(proc, name=name)
        mp = _McpProcess(
            name=name,
            proc=proc,
            client=client,
            on_output=self._on_process_output,
            on_exit=self._on_process_exit,
        )
        with self._lock:
            self._processes[name] = mp
            self._ready[name] = False

        _log.info("MCP server %r started (pid=%d)", name, proc.pid)
        self._emit_started(name)

        # Perform MCP handshake and tool discovery in background
        threading.Thread(
            target=self._init_mcp_protocol, args=(name,),
            daemon=True, name=f"mcp-init-{name}",
        ).start()
        return True

    def stop(self, name: str) -> None:
        """Stop a running server."""
        with self._lock:
            mp = self._processes.pop(name, None)
            self._tools_cache.pop(name, None)
            self._ready.pop(name, None)
            self._rebuild_tool_routing()
        if mp is None:
            return
        mp.stop()
        _log.info("MCP server %r stopped", name)
        self._emit_stopped(name)

    def start_all(self) -> None:
        """Start every enabled server."""
        for name, cfg in self._configs.items():
            if cfg.enabled:
                self.start(name)

    def stop_all(self) -> None:
        """Stop every running server."""
        for name in list(self._processes.keys()):
            self.stop(name)

    def is_running(self, name: str) -> bool:
        with self._lock:
            mp = self._processes.get(name)
        if mp is None:
            return False
        if not mp.is_alive:
            # Process ended; clean up.
            with self._lock:
                self._processes.pop(name, None)
            return False
        return True

    def running_names(self) -> list[str]:
        """Return names of currently running servers."""
        alive = []
        stale = []
        with self._lock:
            for name, mp in self._processes.items():
                if mp.is_alive:
                    alive.append(name)
                else:
                    stale.append(name)
            for s in stale:
                self._processes.pop(s, None)
        return alive

    def get_output(self, name: str) -> list[str]:
        """Return buffered output lines for a server (persists after exit)."""
        with self._lock:
            buf = self._output_buffers.get(name)
        if buf is None:
            return []
        return list(buf)

    # ------------------------------------------------------------------
    # MCP protocol initialisation (runs in background thread)
    # ------------------------------------------------------------------

    def _init_mcp_protocol(self, name: str) -> None:
        """Perform initialize handshake and discover tools."""
        with self._lock:
            mp = self._processes.get(name)
        if mp is None:
            return
        try:
            mp.client.initialize(timeout=30)
            tools = mp.client.list_tools(timeout=15)
            with self._lock:
                self._tools_cache[name] = tools
                self._ready[name] = True
                self._rebuild_tool_routing()
            _log.info("MCP server %r ready – %d tool(s)", name, len(tools))
        except Exception:
            _log.exception("MCP protocol init failed for %r", name)
            self._emit_error(name, "MCP handshake/tool-discovery failed")

    # ------------------------------------------------------------------
    # Tool bridge (for agent loop integration)
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a server name to a safe tool-name component."""
        return re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")

    def _rebuild_tool_routing(self) -> None:
        """Rebuild the namespaced-name → (server, tool) lookup.

        Call while holding ``self._lock``.
        """
        routing: dict[str, tuple[str, str]] = {}
        for server_name, tools in self._tools_cache.items():
            slug = self._slugify(server_name)
            for tool in tools:
                key = f"mcp__{slug}__{tool['name']}"
                routing[key] = (server_name, tool["name"])
        self._tool_routing = routing

    def get_all_mcp_tool_definitions(self, budget: int | None = None) -> list[dict]:
        """Return tool definitions from all ready servers in agent-tool format.

        Parameters
        ----------
        budget:
            Maximum number of MCP tool definitions to return.  When the
            total exceeds *budget* the list is truncated and a warning
            is logged listing every dropped tool.  ``None`` means no cap.

        Each dict has ``{name, description, input_schema}`` matching the
        Anthropic tool schema expected by ``send_with_tools``.
        """
        tools: list[dict] = []
        with self._lock:
            for server_name, raw_tools in self._tools_cache.items():
                if not self._ready.get(server_name):
                    continue
                slug = self._slugify(server_name)
                for t in raw_tools:
                    tools.append({
                        "name": f"mcp__{slug}__{t['name']}",
                        "description": f"[MCP:{server_name}] {t.get('description', '')}",
                        "input_schema": t.get("inputSchema",
                                              {"type": "object", "properties": {}}),
                    })
        if budget is not None and len(tools) > budget:
            dropped = tools[budget:]
            dropped_names = [t["name"] for t in dropped]
            _log.warning(
                "MCP tool budget is %d but %d tool(s) available; "
                "dropping %d tool(s): %s",
                budget, len(tools), len(dropped_names),
                ", ".join(dropped_names),
            )
            tools = tools[:budget]
        return tools

    def is_mcp_tool(self, tool_name: str) -> bool:
        """Return True if *tool_name* is a namespaced MCP tool."""
        return tool_name.startswith("mcp__")

    def call_mcp_tool(self, tool_name: str, arguments: dict,
                      timeout: float = 120) -> str:
        """Route a namespaced MCP tool call to the correct server.

        Returns the text result or an error string.
        """
        with self._lock:
            route = self._tool_routing.get(tool_name)
        if route is None:
            return f"Error: unknown MCP tool '{tool_name}'"

        server_name, real_tool = route

        with self._lock:
            mp = self._processes.get(server_name)
        if mp is None or not mp.is_alive:
            return f"Error: MCP server '{server_name}' is not running"

        try:
            return mp.client.call_tool(real_tool, arguments, timeout=timeout)
        except Exception as exc:
            _log.warning("MCP tool call %s/%s failed: %s",
                         server_name, real_tool, exc)
            return f"Error calling MCP tool: {exc}"

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Stop all servers — call on application exit."""
        self.stop_all()

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    def _emit_started(self, name: str) -> None:
        if self._event_bus is None:
            return
        from core.events import McpServerStartedEvent
        self._event_bus.emit_async(McpServerStartedEvent(name=name))

    def _emit_stopped(self, name: str) -> None:
        if self._event_bus is None:
            return
        from core.events import McpServerStoppedEvent
        self._event_bus.emit_async(McpServerStoppedEvent(name=name))

    def _emit_output(self, name: str, line: str) -> None:
        if self._event_bus is None:
            return
        from core.events import McpServerOutputEvent
        self._event_bus.emit_async(McpServerOutputEvent(name=name, text=line))

    def _emit_error(self, name: str, error: str) -> None:
        if self._event_bus is None:
            return
        from core.events import McpServerErrorEvent
        self._event_bus.emit_async(McpServerErrorEvent(name=name, error=error))

    # ------------------------------------------------------------------
    # Internal callbacks (called from reader threads)
    # ------------------------------------------------------------------

    def _on_process_output(self, name: str, line: str) -> None:
        _log.info("[MCP:%s] %s", name, line)
        with self._lock:
            if name not in self._output_buffers:
                self._output_buffers[name] = deque(maxlen=_MAX_OUTPUT_LINES)
            self._output_buffers[name].append(line)
        self._emit_output(name, line)

    def _on_process_exit(self, name: str, return_code: int | None) -> None:
        # Grab last output lines before removing the process
        with self._lock:
            mp = self._processes.pop(name, None)
            # Clean up tool caches for this server
            self._tools_cache.pop(name, None)
            self._ready.pop(name, None)
            self._rebuild_tool_routing()
        if return_code and return_code != 0:
            tail = ""
            if mp:
                tail = "\n".join(list(mp.output)[-10:])
            msg = f"Process exited with code {return_code}"
            if tail:
                msg += f"\n--- last output ---\n{tail}"
            _log.error("MCP server %r exited with code %d:\n%s",
                       name, return_code, tail)
            self._emit_error(name, msg)
        self._emit_stopped(name)
