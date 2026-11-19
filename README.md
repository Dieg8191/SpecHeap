# SpecHeap

Local-first, open-source workspace for **Spec-Driven Development (SDD)**.

```
Epic → Feature → Requirement → Spec → Verification
```

SpecHeap keeps the full traceability graph of your intent and exposes it to humans (CLI / web UI)
and to AI agents (MCP server). AI proposes, humans approve.

Status: early development. See [docs/mcp-scope.md](docs/mcp-scope.md) for the MVP MCP scope.

## Usage

```bash
specheap init                 # create .specheap/ in the current project
specheap mcp                  # run the MCP server over stdio (add --readonly for read tools only)
specheap serve                # local web UI at http://127.0.0.1:8765 (review queue, tree, approval)
specheap approve REQ-001      # humans approve; agents can only propose
specheap gaps                 # list traceability gaps
```

Connect an MCP client (for example Claude Code) by running the server from your project:

```json
{
  "mcpServers": {
    "specheap": {
      "command": "<path-to>/.venv/Scripts/python",
      "args": ["-m", "specheap", "mcp", "--root", "."]
    }
  }
}
```

The web UI binds to loopback by default. Because it can approve items, it validates the `Host`
header, requires a CSRF token on every action and has no authentication: do not expose it to
a network you do not trust (`--host` other than loopback prints a warning).

The MCP server exposes 7 read tools and 7 write tools, plus resources and prompts. Approval is
intentionally not a tool.

## Web UI

The UI is a React + Vite + Material UI single-page app (`frontend/`) served by a small JSON API
(`src/specheap/web/`). The compiled app is written to `src/specheap/web/static/`, which is
git-ignored but bundled into the Python wheel, so build it before running or releasing:

```bash
cd frontend
npm install
npm run build        # outputs to ../src/specheap/web/static
```

For frontend development, run `specheap serve` and, in another terminal, `npm run dev` inside
`frontend/`: Vite hot-reloads the UI and proxies `/api` to the Python server on port 8765.

## Development

```bash
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest                 # backend tests
cd frontend && npm test && npm run typecheck   # frontend tests and type check
```

## License

MIT
