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

The server exposes 7 read tools and 7 write tools, plus resources and prompts. Approval is
intentionally not a tool.

## Development

```bash
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

## License

MIT
