# poslovi-mcp

MCP server + CLI for searching Serbian job boards — [poslovi.infostud.com](https://poslovi.infostud.com)
and [helloworld.rs](https://www.helloworld.rs) — from Claude (or any MCP client) or straight
from your terminal.

No API keys, no accounts: it reads the public listing pages and the schema.org
`JobPosting` JSON-LD that both boards embed on every posting.

```
$ poslovi search "ai engineer"
  1. AI Automation & Lead Operations Specialist   Thrive Talent Solutions  [infostud]
     https://poslovi.infostud.com/posao/ai-automation-lead-operations-specialist/...
  2. Senior Data Engineer (Technical Leadership)  Keba d.o.o.  [helloworld]
     https://www.helloworld.rs/posao/Senior-Data-Engineer-Technical-Leadership-Track/...
```

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # or: pip install -e ".[dev]" for tests
```

## CLI

```bash
poslovi search "python developer"              # both boards
poslovi search "ml engineer" --board infostud  # one board
poslovi search "devops" --page 2               # pagination
poslovi show <posting-url>                     # full posting text + deadline
```

## MCP server

The same functionality as two MCP tools, `search_jobs` and `get_job`,
served over stdio:

```bash
# Claude Code
claude mcp add poslovi -- /path/to/poslovi-mcp/.venv/bin/poslovi-mcp
```

or in any MCP client config:

```json
{
  "mcpServers": {
    "poslovi": {
      "command": "/path/to/poslovi-mcp/.venv/bin/poslovi-mcp"
    }
  }
}
```

Then just ask: *"nađi mi AI poslove u Beogradu i izdvoji one sa LLM iskustvom"* —
the model searches, opens the interesting ones, and reasons over the full
posting text.

## How it works

- `boards.py` — one parser for both boards (they share a platform): listing
  pages are matched by the `/posao/{slug}/{company}/{id}` URL pattern, detail
  pages by their `JobPosting` JSON-LD block, with page text as fallback.
- `server.py` — [FastMCP](https://github.com/modelcontextprotocol/python-sdk)
  server exposing `search_jobs` / `get_job`.
- `cli.py` — standalone CLI, no MCP client needed.
- `tests/` — offline parser tests against recorded HTML fixtures.

## Tests

```bash
pytest
```
