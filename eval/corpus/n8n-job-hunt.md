# n8n Job Hunt Pipeline

n8n workflow koji svaki dan u 9h skenira srpske job board-ove
([poslovi.infostud.com](https://poslovi.infostud.com) i
[helloworld.rs](https://www.helloworld.rs)), izbaci već viđene oglase,
skoruje nove prema profilu (junior AI/ML/Python ↑, senior/mobile ↓)
i generiše HTML digest + macOS notifikaciju.

Izvor podataka je [poslovi-mcp](https://github.com/umilutinovic25-hash/poslovi-mcp) —
`fetch_jobs.py` je tanak wrapper oko njegove `search_all()` funkcije koji vraća JSON.

## Arhitektura

```
Schedule Trigger (9h, Europe/Belgrade)
  → Execute Command  (fetch_jobs.py → JSON sa oba board-a)
  → Code             (dedupe preko workflow static data + keyword skoring)
  → IF               (ima li novih oglasa?)
  → Code             (HTML digest, base64)
  → Execute Command  (upiši digests/digest-YYYY-MM-DD.html + osascript notifikacija)
```

Dedupe koristi n8n **workflow static data** (`$getWorkflowStaticData`) — URL-ovi
viđenih oglasa se pamte između pokretanja, pa digest sadrži samo nove oglase.
Napomena: static data se čuva samo kod produkcionih pokretanja (aktivan workflow
ili `n8n execute`), ne kod ručnog testa u editoru.

## Setup

```bash
# preduslovi: Node 22+, poslovi-mcp instaliran u ~/poslovi-mcp/.venv
npm install -g n8n

# uvezi workflow
n8n import:workflow --input=workflow.json

# jednokratno pokretanje iz terminala
NODES_EXCLUDE="[]" n8n execute --id JobHuntPipeline0

# ili otvori editor (workflow je vec aktivan, schedule radi dok n8n radi)
NODES_EXCLUDE="[]" n8n start   # → http://localhost:5678
```

> **Napomena za n8n 2.x**: Execute Command node je podrazumevano isključen
> iz bezbednosnih razloga (`nodes.exclude` default). `NODES_EXCLUDE="[]"`
> ga vraća — neophodno i za `execute` i za `start`.

## Konfiguracija

- **Upiti**: env promenljiva `JOB_QUERIES` (zapetom razdvojeni), default:
  `ai engineer,machine learning,python developer,llm engineer`
- **Skoring**: `KEYWORDS` lista u "Dedupe & Score" Code node-u
- **Vreme**: Schedule Trigger node (default 9:00, Europe/Belgrade)

## Digest

Snima se u `digests/digest-YYYY-MM-DD.html` — tabela sortirana po skoru sa
linkovima ka oglasima, firmom, board-om i upitom koji ga je pronašao.

## Moguće nadogradnje

- Anthropic node umesto keyword skoringa — LLM oceni oglas prema celom CV-ju
  (preko `poslovi show <url>` punog teksta oglasa)
- Gmail/Telegram node umesto lokalne notifikacije
- Google Sheets node za praćenje prijava
