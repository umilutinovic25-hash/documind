# dine-agent

An AI phone host for a restaurant. It answers the call, works out what the guest
wants, and manages the reservation book — checking availability, booking, moving
and cancelling tables.

The interesting part is not the chat. It is that **the agent cannot invent a
table.** Every write goes through a booking engine that owns the restaurant's
policy: service windows, table capacities, dining durations, turnaround buffers,
and conflict detection. The model proposes; the engine decides. A hallucinated
time is rejected, not persisted.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000, press **Call**, and speak. Speech in and speech out
run in the browser (Web Speech API), so the demo costs nothing and needs no
account. Chrome is required for the microphone; typing works anywhere.

With no `ANTHROPIC_API_KEY` set, the app runs a **scripted fallback** — a
keyword-driven script that walks the happy path and calls the same real tools.
It is there so the booking engine and the UI can be exercised end to end; it is
not language understanding. Export a key to get the actual agent:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

The badge in the header tells you which brain is answering.

## How it fits together

```
browser (speech in/out)
   |  text
   v
FastAPI  ──►  Agent (Claude tool-use loop)  ──►  booking engine  ──►  SQLite
                     │                                  ▲
                     └── check_availability             │
                         book_table            the only writer
                         find_reservation
                         modify_reservation
                         cancel_reservation
```

`Agent.reply()` takes text and returns text. It knows nothing about microphones
or phone lines — which is what makes the voice layer swappable.

## The booking engine

`app/config.py` is the restaurant: eight tables from two-tops to an eight-top,
lunch and dinner services, closed Mondays.

`app/booking.py` enforces it:

- **Turn times** scale with party size — a couple holds a table 90 minutes, a
  party of eight holds it 150.
- **A turnaround buffer** (15 min) sits either side of every booking, so a table
  is not resold the instant the previous guests stand up.
- **Conflict detection** compares the requested window against every existing
  booking on that table, buffer included.
- **Table assignment** picks the smallest table that fits, so a couple doesn't
  consume the only eight-top.
- **Modify re-checks availability** against everything *except the booking being
  moved* — and if the new slot is unavailable, the original is left untouched
  rather than dropped.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

Fourteen tests over the engine — capacity, closed days, off-grid times, the
buffer, cancel-frees-the-table, and the two failure modes worth losing sleep
over: a modify colliding with itself, and a failed modify destroying the
booking it was meant to change.

## Putting it on a real phone number

The agent is transport-agnostic, so the voice layer is the only new code:

1. Buy a number and point its voice webhook at a new `/twilio/voice` route.
2. Stream the call audio (Twilio Media Streams) to a speech-to-text service.
3. Feed each final transcript to `Agent.reply()` — the same call the browser makes.
4. Send the reply to a text-to-speech voice and play it back down the line.
5. Key `CALLS` by Twilio's `CallSid` instead of a generated id, and move it out
   of process memory into Redis.

Nothing in `agent.py`, `tools.py`, or `booking.py` changes.

## Shortcuts taken

Honest list, since this is a demo:

- Calls live in a process-local dict, so the app is single-instance.
- No authentication — anyone who knows a code can cancel that booking.
- The engine assumes one seating grid for the whole room; it does not model
  sections, servers, or walk-ins.
