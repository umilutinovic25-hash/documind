# JobScout

An AI agent that analyzes job postings against your CV: it scrapes the posting,
extracts structured requirements with Claude, scores the match against your CV
with a calibrated rubric, drafts a tailored cover letter, and tracks every
application (with per-application API cost) in SQLite.

Built as a real tool for my own job search — every application I send goes
through it.

```
┌─────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────────┐
│ scraper  │──▶│ extraction    │──▶│ CV matching   │──▶│ cover letter   │
│ httpx+bs4│   │ Claude,       │   │ Claude,       │   │ Claude         │
│          │   │ structured    │   │ 0-100 rubric  │   │ ≤250 words     │
└─────────┘   │ output        │   │ + gaps        │   └───────────────┘
              └──────────────┘   └──────────────┘
                        │                │                     │
                        └────────────────┴────────┬────────────┘
                                                  ▼
                                       SQLite (status + cost tracking)
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env          # add your ANTHROPIC_API_KEY
.venv/bin/jobscout import-cv path/to/your_cv.pdf
```

## Usage

```bash
# Analyze a posting (URL, file, or pasted text)
jobscout add https://example.com/careers/ai-engineer
jobscout add --file posting.txt

# Review the pipeline's verdict
jobscout list                 # sorted by match score
jobscout show 3               # full analysis: matched skills, gaps, talking points

# Generate a cover letter (language follows the posting; --lang overrides)
jobscout letter 3
jobscout letter 3 --lang sr

# Track the application
jobscout status 3 applied     # new → applied → interview → offer/rejected
```

There is also a FastAPI backend exposing the same pipeline
(`uvicorn jobscout.api:app`) — the base for the React dashboard (iteration 2).

## Design decisions

- **Two Claude calls instead of one** (extract → match): each step has a single
  responsibility, produces a typed Pydantic object via structured outputs, and
  can be evaluated and regression-tested independently.
- **Honest scoring over flattery**: the match prompt uses an explicit 0-100
  rubric and only counts a requirement as met when the CV contains concrete
  evidence, not a keyword. An inflated score wastes the user's time.
- **Cost tracking built in**: every token in/out is recorded per application;
  `jobscout list` shows the running total. A full analysis costs roughly
  $0.05–0.10 with Claude Opus 4.8.
- **No headless browser**: JS-rendered postings fail fast with a clear message
  and a `--file`/`--text` fallback, instead of dragging in Playwright for v1.
- **SQLite, stdlib only**: one file, zero infrastructure, trivially portable.

## Tests

```bash
.venv/bin/pytest
```

Unit tests cover the DB layer and HTML-to-text cleaning. Next: an eval suite
with golden job postings to regression-test extraction and match scoring
whenever a prompt changes.

## Roadmap

- [ ] Eval pipeline: golden postings + expected extractions, scored on every prompt change
- [ ] React dashboard on top of the FastAPI backend
- [ ] Batch mode: analyze a list of URLs in one run (Anthropic Batches API, 50% cheaper)
- [ ] Deploy (Docker + Fly.io/Railway)
