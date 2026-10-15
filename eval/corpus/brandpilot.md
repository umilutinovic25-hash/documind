# 🚀 BrandPilot

AI marketing content generator. Give it a company website URL — it scrapes the
site, derives a **brand profile** (offering, audience, tone, USPs), builds a
**two-week content calendar**, and writes **ready-to-publish posts** for
LinkedIn and Instagram, each with hashtags and an image brief for a designer.

```
$ brandpilot plan https://acme.example --posts 6 --out plan.md
provider: anthropic
written: plan.md
```

## How it works

```
URL → scraper (httpx + BeautifulSoup: homepage + about/services page)
    → analyze_brand   (LLM → brand profile JSON)
    → plan_content    (LLM → content calendar JSON)
    → write_post ×N   (LLM → copy + hashtags + image brief per post)
    → markdown report / Gradio UI
```

All three LLM stages use **structured outputs** (`output_config.format` with a
JSON schema) on the Anthropic API (`claude-opus-4-8`), so responses are
guaranteed-parseable JSON — no brittle prompt-and-pray parsing.

## Providers

| Provider | When | What |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` set (or `BRANDPILOT_PROVIDER=anthropic`) | Real Claude calls with adaptive thinking + structured outputs |
| `mock` | default fallback | Deterministic, schema-conforming output seeded from the scraped site — full pipeline runs offline, used by the test suite and demos |

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[demo,dev]"

pytest                       # 6 tests, offline (mock provider)
brandpilot analyze <url>     # brand profile as JSON
brandpilot plan <url> --posts 6 --out plan.md
python app.py                # Gradio demo → http://localhost:7864
```

## Example output

See [`demo-plan.md`](demo-plan.md) — generated from a live client website with
the mock provider (no API key needed).

## n8n automation

[`n8n/workflow.json`](n8n/workflow.json) wires BrandPilot into
[n8n](https://n8n.io): every **Monday at 8:00** it walks a client list (Code
node), runs `brandpilot plan` per client (Execute Command), writes the plans to
`plans/<client>-<date>.md`, and sends a macOS notification with an ok/failed
summary.

```bash
n8n import:workflow --input=n8n/workflow.json
NODES_EXCLUDE="[]" n8n execute --id BrandPilotPipeline0   # run once, from terminal
NODES_EXCLUDE="[]" n8n start                              # editor + weekly schedule
```

> n8n 2.x disables the Execute Command node by default — `NODES_EXCLUDE="[]"`
> re-enables it. Clients are configured in the "Lista klijenata" Code node.

## Possible next steps

- Direct publishing via platform APIs (extend the n8n workflow)
- Image generation from the image briefs
- Multi-language output (the pipeline is language-agnostic — the brand profile
  carries the tone)
