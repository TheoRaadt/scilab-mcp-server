#!/usr/bin/env python3
"""MCP server exposing a persistent Scilab console."""

import os
import re
import threading

import pexpect

try:
    from mcp.server.fastmcp import FastMCP as MCPServer
except ImportError:
    # Newer `mcp` releases renamed/moved FastMCP to MCPServer.
    from mcp.server.mcpserver import MCPServer

SCILAB_BIN = os.environ.get("SCILAB_BIN", "scilab")
PROMPT = r"-->"
TIMEOUT = int(os.environ.get("SCILAB_TIMEOUT", "60"))

mcp = MCPServer("scilab")

_lock = threading.Lock()
_child: pexpect.spawn | None = None

_CSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _render(raw: str) -> str:
    """Strip ANSI escapes and replay backspaces to reconstruct plain text.

    Scilab's -nw console echoes typed input character-by-character wrapped
    in insert-mode escapes, padded with a trailing space+backspace per char.
    A naive strip leaves those stray spaces in the wrong place, so backspace
    is replayed against a buffer to get the text as it would actually render.
    """
    text = _CSI_RE.sub("", raw).replace("\r", "")
    buf: list[str] = []
    for ch in text:
        if ch == "\x08":
            if buf:
                buf.pop()
        else:
            buf.append(ch)
    return "".join(buf)


def _start():
    global _child
    child = pexpect.spawn(
        SCILAB_BIN,
        ["-nw"],
        encoding="utf-8",
        codec_errors="replace",
        timeout=TIMEOUT,
    )
    child.expect(PROMPT)
    _child = child


def _ensure_started():
    if _child is None or not _child.isalive():
        _start()


def _run(code: str) -> str:
    """Send code to the running Scilab process and return its output."""
    _ensure_started()
    assert _child is not None
    child = _child

    sentinel = "__SCILAB_MCP_DONE__"
    child.sendline(code)
    child.sendline(f'disp("{sentinel}")')
    # Match the opening quote too, so its leading indent doesn't leak into `before`.
    child.expect(f'"{sentinel}')
    rendered = _render(child.before)

    # Drop the echoed input lines and prompts, keeping only real output.
    sent_lines = {l.strip() for l in code.splitlines()}
    sent_lines.add(f'disp("{sentinel}")')
    cleaned = []
    for line in rendered.split("\n"):
        if line.startswith(PROMPT):
            line = line[len(PROMPT):]
        stripped = line.strip()
        if stripped == "" or stripped in sent_lines:
            continue
        cleaned.append(line.rstrip())

    child.expect(PROMPT)
    return "\n".join(cleaned).strip()


@mcp.tool()
def execute(code: str) -> str:
    """Run one or more lines of Scilab code in the persistent session and
    return any printed output. End statements with ';' to suppress Scilab's
    auto-echo of results."""
    with _lock:
        try:
            return _run(code)
        except pexpect.TIMEOUT:
            return f"Error: Scilab did not respond within {TIMEOUT}s (command may still be running)."
        except pexpect.EOF:
            global _child
            _child = None
            return "Error: Scilab process died. It will be restarted on the next call."


@mcp.tool()
def run_file(path: str) -> str:
    """Run a Scilab .sce/.sci file via exec() and return any printed output."""
    if not os.path.isfile(path):
        return f"Error: file not found: {path}"
    escaped = path.replace("\\", "\\\\").replace('"', '\\"')
    with _lock:
        try:
            return _run(f'exec("{escaped}", -1)')
        except pexpect.TIMEOUT:
            return f"Error: Scilab did not respond within {TIMEOUT}s (command may still be running)."
        except pexpect.EOF:
            global _child
            _child = None
            return "Error: Scilab process died. It will be restarted on the next call."


@mcp.tool()
def get_variable(name: str) -> str:
    """Print the current value of a Scilab variable."""
    if not re.match(r"^[A-Za-z%_][A-Za-z0-9_%#!$]*$", name):
        return f"Error: invalid variable name: {name}"
    with _lock:
        try:
            out = _run(f"disp({name})")
            return out if out else f"Error: variable '{name}' is not defined or empty."
        except pexpect.TIMEOUT:
            return f"Error: Scilab did not respond within {TIMEOUT}s."
        except pexpect.EOF:
            global _child
            _child = None
            return "Error: Scilab process died. It will be restarted on the next call."


@mcp.tool()
def reset() -> str:
    """Restart the Scilab process, clearing all state."""
    global _child
    with _lock:
        if _child is not None and _child.isalive():
            _child.close(force=True)
        _child = None
        _start()
    return "Scilab session reset."


@mcp.tool()
def status() -> str:
    """Check whether a Scilab session is currently running."""
    with _lock:
        if _child is not None and _child.isalive():
            return f"Running (pid {_child.pid})."
        return "Not running."


if __name__ == "__main__":
    mcp.run()
