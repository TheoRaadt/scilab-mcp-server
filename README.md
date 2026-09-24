# Scilab MCP Server

Exposes a persistent Scilab console as MCP tools: `execute`, `run_file`,
`get_variable`, `reset`, `status`. Variables and state persist across calls,
like FreeCAD's server keeps a document open between calls.

This wraps Scilab's own command-line console (`scilab -nw`) and `exec()`,
which is the simplest of Scilab's documented interop options (the others —
`api_scilab`, Javasci, the Tcl/Tk bridge — are lower-level C/Java APIs meant
for embedding, not quick scripting).

## 1. Install dependencies

```bash
pip install "mcp[cli]" pexpect
```

Note the exact Python interpreter this installs into — you'll need its
absolute path in step 3, since `python3` on your `PATH` inside an
interactive shell can resolve to a different interpreter than what a GUI
app's subprocess sees (see Troubleshooting below).

## 2. Find your Scilab binary

The server needs the actual `scilab` (console) executable, not just the
`.app` bundle. On macOS it's usually inside the app bundle, e.g.:

```
/Applications/scilab-2026.1.0.app/Contents/MacOS/scilab
```

Find it with:

```bash
find /Applications -iname "scilab" -type f 2>/dev/null
```

If it's not on your PATH, set the `SCILAB_BIN` environment variable to the
full path when running the server (see config below).

## 3. Register the server with Claude

Add it to your MCP config (Claude Desktop's `claude_desktop_config.json`, or
a project's `.mcp.json` for Claude Code):

```json
{
  "mcpServers": {
    "scilab": {
      "command": "/absolute/path/to/python3",
      "args": ["/absolute/path/to/scilab_mcp_server.py"],
      "env": {
        "SCILAB_BIN": "/Applications/scilab-2026.1.0.app/Contents/MacOS/scilab"
      }
    }
  }
}
```

Use the interpreter's **absolute path** for `command` — see Troubleshooting.

Restart Claude Desktop (or reload the Claude Code session) after editing
the config.

## Tools

- **execute(code)** — run one or more lines of Scilab code, return printed
  output. End statements with `;` to suppress Scilab's auto-echo.
- **run_file(path)** — run an `.sce`/`.sci` file via `exec()`.
- **get_variable(name)** — print a variable's current value.
- **reset()** — restart the Scilab process, clearing all state.
- **status()** — check whether a session is running.

## Notes / limitations

- One Scilab process is shared across all calls (a lock serializes them),
  so long-running computations will block subsequent calls until they finish.
- Output capture relies on a sentinel `disp()` marker plus stripping ANSI
  escape sequences and replaying backspaces — Scilab's `-nw` console echoes
  typed input character-by-character wrapped in insert-mode terminal codes,
  so a naive strip of escape codes alone leaves stray characters behind.
- Unusual multi-line constructs (e.g. `for`/`end` blocks split across several
  `execute()` calls) may not parse cleanly — prefer sending a whole block in
  a single `execute()` call, or use `run_file()`.
- No plotting support: `-nw` runs Scilab headless (no graphics window), so
  graphics commands like `plot()` will fail or no-op.

## Troubleshooting

**Server shows `CONNECTION_CLOSED` / fails to connect.** This almost always
means `command` in your MCP config resolves to a Python interpreter that
doesn't have `mcp`/`pexpect` installed. A bare `"command": "python3"` relies
on `PATH`, but Claude Desktop and Claude Code spawn the server with a
minimal environment that skips your shell's startup files (`.zshrc`,
`.bash_profile`) — so if those files are what put the right Python on
`PATH` (e.g. a `conda init` block), the subprocess silently falls back to a
different, unpatched interpreter and crashes on import. Fix: set `command`
to the absolute path of the interpreter you ran `pip install` with (find it
via `python3 -c "import sys; print(sys.executable)"` in the same shell you
used for step 1), not just `"python3"`.
