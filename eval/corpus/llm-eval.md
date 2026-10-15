# llm-eval

A small framework for comparing LLMs on the same set of tasks — measuring
**accuracy, cost, and latency** side by side, and saving each run as a JSON
snapshot so you can catch regressions over time.

Evals are defined as YAML, not code, so adding a new test is a config change.
The runner is async, tracks token usage and cost per request, and prints a
comparison table.

```
$ llm-eval evals/classification.yaml -p claude:claude-opus-4-8 -p ollama:llama3.2

              Eval: classification  (2026-07-06T19:02:11)
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Provider                ┃ Pass rate ┃ Errors ┃ Latency p50 ┃ Latency p95 ┃ Cost (run) ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ claude:claude-opus-4-8  │       3/3 │      0 │       0.9s  │       1.4s  │    $0.0021 │
│ ollama:llama3.2         │       2/3 │      0 │       0.4s  │       0.7s  │       free │
└─────────────────────────┴───────────┴────────┴─────────────┴─────────────┴────────────┘
```

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # core (mock + ollama providers)
pip install -e '.[claude]'  # add the Anthropic provider
```

## Run

```bash
llm-eval evals/smoke.yaml -p mock                     # offline, no keys needed
llm-eval evals/extraction.yaml -p ollama:llama3.2     # local model via Ollama
llm-eval evals/extraction.yaml \
    -p claude:claude-opus-4-8 -p claude:claude-haiku-4-5   # compare two Claude models
```

Providers are passed with `-p` (repeatable). Every run writes a JSON snapshot
to `results/`. Exit code is non-zero if any case fails, so it works as a CI gate.

### HTML report

Aggregate snapshots into one self-contained, theme-aware HTML dashboard
(pass-rate bars, latency, cost — no external assets, opens anywhere):

```bash
llm-eval-report                       # latest snapshot per eval in results/
llm-eval-report results/*.json -o report.html
```

### Providers

| Spec                       | Backend            | Needs                    |
| -------------------------- | ------------------ | ------------------------ |
| `mock`                     | fake, offline      | nothing                  |
| `ollama:<model>`           | local via Ollama   | Ollama running locally   |
| `claude:<model>`           | Anthropic API      | `ANTHROPIC_API_KEY`      |

## Writing an eval

```yaml
name: classification
grader: exact_match        # default grader for all cases
system: >                  # optional system prompt sent to every provider
  Classify the sentiment as exactly one word: positive, negative, or neutral.
cases:
  - id: clearly-positive
    prompt: "Shipping was fast and the quality is excellent!"
    expected: positive
  - id: garbage
    prompt: "..."
    expected: neutral
    grader: contains       # per-case override of the eval-level grader
```

### Graders

| Grader        | Passes when…                                                     |
| ------------- | ---------------------------------------------------------------- |
| `exact_match` | normalized response equals expected                             |
| `contains`    | expected substring is in the response                          |
| `regex`       | expected pattern matches the response                          |
| `json_fields` | first JSON object in the response matches every expected key    |
| `llm_judge`   | a judge model decides PASS/FAIL against a rubric (open-ended answers) |

### LLM-as-judge

For open-ended answers where `exact_match` can't work, `llm_judge` hands the
question, the candidate answer, and a rubric to a *judge* model, which returns a
`VERDICT: PASS`/`FAIL` line plus a one-line reason. Set the judge per eval:

```yaml
grader: llm_judge
judge: claude:claude-opus-4-8    # any provider — claude:*, ollama:*
cases:
  - id: explain-rag
    prompt: "In one sentence, what problem does RAG solve?"
    expected: >                  # here `expected` is the rubric, not a literal answer
      Must convey that RAG grounds the model in retrieved external documents,
      reducing hallucination and covering data outside its training set.
```

The judge is asked to reason *before* committing to a verdict (this reduces
leniency bias versus a bare yes/no). Judge tokens cost money but are
deliberately kept out of the model-under-test's cost column so the comparison
stays honest. See `src/llm_eval/graders/judge.py`.

Override the judge from the CLI (handy for judging offline with a local model):

```bash
llm-eval evals/judge_demo.yaml -p ollama:llama3.2 --judge ollama:llama3.2
```

## Included evals

| File                    | Grader        | What it tests                                            |
| ----------------------- | ------------- | ------------------------------------------------------- |
| `smoke.yaml`            | exact_match   | Framework sanity check (offline, mock provider)         |
| `classification.yaml`   | exact_match   | Sentiment labels — cheap smoke test for any provider    |
| `extraction.yaml`       | json_fields   | Structured fields from job ads (JobScout use case)      |
| `extraction_hard.yaml`  | json_fields   | 4 fields from denser ads — discriminates model quality  |
| `reasoning.yaml`        | regex         | Word/logic problems that separate models by capability  |
| `judge_demo.yaml`       | llm_judge     | Open-ended answers graded against a rubric              |

A real 3-model local run (llama3.2, qwen2.5:3b, mistral) spreads them out:
qwen leads on reasoning (4/5), llama on the hard extraction (3/4), and the
weaker model both scores lowest and occasionally emits invalid JSON — which
`json_fields` catches. The harder evals are meant to be failed; that's how they
tell models apart.

## Cost tracking

Cost is computed from each response's token usage against the published
per-million-token prices in `src/llm_eval/metrics.py`. Local models (Ollama,
mock) are always free. Update `PRICING` when Anthropic prices change.

## Tests

```bash
python -m unittest discover -s tests -v
```

CI (`.github/workflows/ci.yml`) runs the unit tests plus the offline smoke eval
on every push — no API keys required.
