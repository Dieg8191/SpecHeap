# SpecHeap

**A local-first workspace for Spec-Driven Development.** SpecHeap keeps the full chain from
business intent to proof, lets AI agents write specifications through [MCP](https://modelcontextprotocol.io),
and keeps a human in charge of approving them.

```
Epic  →  Feature  →  Requirement  →  Spec  →  Verification
 why       what         must hold      how        proof
```

Specs written by AI are only useful if you can trust them. SpecHeap makes that trust explicit:
agents can create and propose, **only humans can approve**, and nothing is "verified" until a
verification actually passed.

> **Status: early development (v0.1).** The core, the MCP server, the web UI and the CLI work and
> are covered by tests. It is not published to PyPI yet; see [Status and roadmap](#status-and-roadmap).

## Highlights

- **Traceability you can query.** Every requirement links to the specs that satisfy it and the
  verifications that prove it. Gaps (a requirement with no spec, a spec nobody verifies, a failing
  test) are reported on demand.
- **AI proposes, humans approve.** The rule lives in the core, not in the interfaces: an agent that
  tries to approve gets `FORBIDDEN_FOR_AGENT`, and the MCP server has no approve tool at all.
- **"Verified" means proven.** An item becomes `verified` by itself when all its verifications pass,
  and goes `stale` if one later fails. Nobody can assert it by hand.
- **Changes ripple.** Editing an approved requirement sends it back to review and marks every spec
  and verification built on it as `stale`, so nothing silently drifts.
- **Safe with several writers.** One SQLite file, atomic multi-step operations, unique ids and
  optimistic concurrency, so an agent over MCP and you in the browser can work at the same time.
- **Three interfaces, one set of rules.** MCP for agents, a web UI for review, a CLI for scripts and
  CI. They all go through the same service layer.

## How it works

### Items

| Level | Answers | Example |
|---|---|---|
| **Epic** | Which goal? | *Traceable specification workspace* |
| **Feature** | Which capability? | *Lifecycle and review workflow* |
| **Requirement** | What must hold? | *WHEN an agent tries to approve, THE SYSTEM SHALL reject it* |
| **Spec** | How is it built? | *Actor-based permissions: modules, contracts, decisions* |
| **Verification** | How do we prove it? | *`pytest tests/test_lifecycle.py::test_agent_cannot_approve`* |

Ids are stable and readable: `EPIC-001`, `FEAT-003`, `REQ-012`, `SPEC-007`, `VER-020`. A spec can
also satisfy other requirements, and a verification can also verify other requirements or specs,
through typed links.

### Lifecycle

```
draft ──▶ proposed ──▶ approved ──▶ implemented ──▶ verified
                          ▲                             │
                          └──── stale ◀── upstream change / failed verification
```

| Transition | Human | AI agent | System |
|---|:-:|:-:|:-:|
| create → `draft` | ✅ | ✅ | |
| `draft` → `proposed` | ✅ | ✅ | |
| `proposed` → `approved` | ✅ | ❌ | |
| `stale` → `approved` | ✅ | ❌ | |
| `approved` → `implemented` | ✅ | ✅ | |
| `implemented` → `verified` | | | ✅ derived |
| anything reviewed → `stale` | | | ✅ derived |

Only requirements and specs are implemented and verified; epics, features and verifications stop
at `approved`.

## Quick start

SpecHeap is not on PyPI yet, so install it from source. You need Python 3.12+ and, to build the
web UI, a recent Node.js.

```bash
git clone https://github.com/Dieg8191/SpecHeap.git
cd SpecHeap

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .

cd frontend
npm install
npm run build                        # builds the web UI into the Python package
cd ..
```

Then, inside the project you want to specify:

```bash
specheap init       # creates .specheap/specheap.db
specheap serve      # review UI at http://127.0.0.1:8765
```

Connect an agent (next section), let it propose requirements, and approve them in the browser.

## Connect an AI agent

`specheap mcp` is a standard MCP server over **stdio**, so any client that can launch a stdio
server can use it. For example, with a `.mcp.json` at the root of your project (Claude Code):

```json
{
  "mcpServers": {
    "specheap": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "specheap", "mcp", "--root", "."]
    }
  }
}
```

On Windows the command is `C:\path\to\.venv\Scripts\python.exe`. Add `--readonly` to expose only
the read tools.

### What the agent gets

| Read tools | Write tools |
|---|---|
| `get_overview`: counts, coverage, gaps | `create_item`: always starts as `draft` |
| `list_items`: filtered, paginated | `update_item`: needs the revision you last read |
| `get_item` | `propose_item`: ask for human review |
| `get_context`: an item with its ancestors and descendants (the best first call) | `link_items` / `unlink_items` |
| `trace`: up to the epic, down to the proofs | `mark_implemented` |
| `list_gaps` | `report_verification`: pass, fail or skipped, with evidence |
| `next_work`: approved items ready to build | |

There is no approval tool. The server also offers resources (`specheap://overview`,
`specheap://{type}/{id}`, `specheap://feature/{id}/context`) and four guided prompts:
`decompose_feature`, `draft_specs`, `plan_verifications` and `review_gaps`.

A typical session: ask the agent to run `decompose_feature` on a feature, then `draft_specs` and
`plan_verifications` for each requirement. Everything lands as `proposed` in your review queue.

Errors are structured (`code`, `message`, `hint`) so an agent can recover on its own, for example
`REVISION_CONFLICT` tells it to re-read the item and retry.

## Web UI

`specheap serve` starts a React + Material UI app with:

- an **overview**: items, requirement coverage, open gaps, a status distribution bar;
- a **review queue** of proposed and stale items, each with an Approve button;
- a **traceability tree** with filters by text and status and per-requirement verification progress;
- an **item page**: lifecycle stepper, highlighted EARS requirements, verification results with
  their evidence, and the lifecycle actions you are allowed to take. Light and dark themes.

The UI can approve specs and has no login, so it is built for local use: it binds to loopback,
validates the `Host` header, requires a CSRF token for every action and sends a strict
Content-Security-Policy. Binding to another interface prints a warning; do not expose it to a
network you do not trust.

## Command line

```bash
specheap init                 # create the workspace database
specheap serve                # web UI (--host, --port, --allowed-host)
specheap mcp                  # MCP server over stdio (--readonly)
specheap approve REQ-012      # approve a proposed item, as a human
specheap gaps                 # list traceability gaps; exits 1 if there are any (handy for CI)
specheap gaps --scope FEAT-003
```

Every command takes `--root DIR` (default: the current directory).

## Storage

A workspace is one **SQLite database**, `.specheap/specheap.db`, and it is the only source of
truth. The MCP server, the web UI and the CLI can run against it at the same time, each in its own
process:

- multi-step operations are **atomic**: an edit that marks dependents stale, a result that makes a
  requirement verified, or creating an item either fully happens or not at all;
- writers are serialized, so concurrent agents get **unique ids** and an edit made with an outdated
  revision is rejected instead of overwriting someone else's;
- every change, including the ones the system derives, is recorded in the `audit_log` table;
- the schema is versioned, so future releases can migrate it.

Details, schema and backups: [docs/storage.md](docs/storage.md).

## Project layout

```
MCP server ─┐
Web API ────┼──▶ Service(actor) ──▶ Storage (SQLite)
CLI ────────┘     rules live here
```

```
src/specheap/
  core/       models, lifecycle rules, graph, service, errors (no I/O, no interface code)
  storage/    SQLite adapter and an in-memory adapter for tests
  mcp/        MCP server: a thin adapter over the service, always acting as the agent
  web/        JSON API that also serves the compiled frontend
  cli.py      the `specheap` command
frontend/     React + Vite + Material UI single-page app
tests/        backend tests, run against every storage adapter
docs/         design notes
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest                       # backend tests (memory and SQLite adapters)
ruff check .                           # lint

cd frontend
npm test && npm run typecheck          # frontend tests and type check
npm run dev                            # hot-reloading UI, proxies /api to `specheap serve`
```

The compiled UI is written to `src/specheap/web/static/`, which is git-ignored but bundled into
the Python wheel. Build it (`npm run build`) before packaging a release.

## Status and roadmap

**Works today:** the traceability model and lifecycle, atomic SQLite storage, the MCP server
(verified end to end over a real stdio connection with the official SDK client), the review UI and
the CLI.

**Not done yet:**

- Not published to PyPI, so `uvx specheap` does not work yet; there is no CI.
- The MCP server has been exercised through the SDK client but not yet through an interactive
  agent such as Claude Code. That is the next validation step.
- The UI reviews and approves but does not edit item content; agents and the API do.
- No authentication or multi-user hosting. The web UI is local-only by design for now.

**Planned:** item history and diffs (an `item_versions` table, see
[docs/storage.md](docs/storage.md)), a "code mode" where agents write scripts against the service
instead of chaining tool calls, accessibility work on the UI, and an optional hosted mode.

## Documentation

- [docs/storage.md](docs/storage.md): database schema, transactions, concurrency, migrations.
- [docs/mcp-scope.md](docs/mcp-scope.md): scope and design of the MCP interface (in Spanish).

## License

[MIT](LICENSE)
