# SpecHeap

Local-first, open-source workspace for **Spec-Driven Development (SDD)**.

```
Epic → Feature → Requirement → Spec → Verification
```

SpecHeap keeps the full traceability graph of your intent and exposes it to humans (CLI / web UI)
and to AI agents (MCP server). AI proposes, humans approve.

Status: early development. See [docs/mcp-scope.md](docs/mcp-scope.md) for the MVP MCP scope.

## Development

```bash
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

## License

MIT
