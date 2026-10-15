import { useEffect, useRef, useState } from "react";

async function* sse(res) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const event = /event: (.*)/.exec(raw)?.[1];
      const data = /data: (.*)/s.exec(raw)?.[1];
      if (event && data) yield { event, data: JSON.parse(data) };
    }
  }
}

async function errorText(res) {
  try {
    return (await res.json()).detail ?? res.statusText;
  } catch {
    return res.statusText;
  }
}

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function highlight(text, question) {
  const words = [...new Set(question.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((w) => w.length > 3))];
  if (!words.length) return text;
  const re = new RegExp(`(${words.map((w) => escapeRe(w.slice(0, Math.max(4, w.length - 2)))).join("|")}[\\p{L}]*)`, "giu");
  return text.split(re).map((part, i) => (i % 2 ? <mark key={i}>{part}</mark> : part));
}

// Turns "[2]" in an answer into clickable chips; unsupported ones are flagged.
function renderAnswer(text, verification, onCite) {
  const bad = new Set();
  const moved = new Map(); // cited [n] -> the source that actually contains the claim
  verification?.checks?.forEach((c) => {
    if (!c.supported) c.cites.forEach((n) => bad.add(n));
    else if (c.misattributed && c.found_in) c.cites.forEach((n) => moved.set(n, c.found_in));
  });
  const invalid = new Set(verification?.invalid_citations ?? []);
  return text.split(/(\[\d+(?:\s*[,;]\s*\d+)*\])/g).flatMap((part, i) => {
    const m = /^\[(\d+(?:\s*[,;]\s*\d+)*)\]$/.exec(part);
    if (!m) return [part];
    return m[1].split(/\s*[,;]\s*/).map((num) => citeChip(Number(num), `${i}-${num}`));
  });
  function citeChip(n, key) {
    const cls = invalid.has(n) ? "cite invalid" : bad.has(n) ? "cite weak" : moved.has(n) ? "cite moved" : "cite";
    const title = invalid.has(n)
      ? "Nepostojeći izvor"
      : bad.has(n)
        ? "Tvrdnja slabo podržana izvorom"
        : moved.has(n)
          ? `Tvrdnja je tačna, ali podatak je u izvoru [${moved.get(n)}]`
          : "Otvori izvor";
    return (
      <button key={key} type="button" className={cls} title={title} onClick={(e) => (e.stopPropagation(), onCite(moved.get(n) ?? n))}>
        {n}
      </button>
    );
  }
}

export default function App() {
  const [docs, setDocs] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState(null);
  const [active, setActive] = useState(null);
  const [focusSrc, setFocusSrc] = useState(null);
  const [view, setView] = useState("chat");
  const [reviewQs, setReviewQs] = useState("");
  const [grid, setGrid] = useState(null);
  const [reviewing, setReviewing] = useState(false);
  const fileRef = useRef();
  const endRef = useRef();

  async function refresh() {
    try {
      const res = await fetch("/api/documents");
      if (res.ok) setDocs(await res.json());
    } catch {
      setNotice({ kind: "error", text: "Server nije dostupan." });
    }
  }
  useEffect(() => {
    refresh();
  }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function upload(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setNotice(null);
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch("/api/documents", { method: "POST", body });
      if (!res.ok) throw new Error(await errorText(res));
      const d = await res.json();
      setNotice({
        kind: "ok",
        text: d.duplicate
          ? `${d.doc} je već učitan.`
          : `${d.doc}: ${d.chunks} delova${d.ocr_pages ? `, OCR na ${d.ocr_pages} str.` : ""}.`,
      });
      await refresh();
    } catch (err) {
      setNotice({ kind: "error", text: String(err.message ?? err) });
    } finally {
      setUploading(false);
      fileRef.current.value = "";
    }
  }

  async function remove(id) {
    await fetch(`/api/documents/${id}`, { method: "DELETE" });
    setSelected((s) => {
      const n = new Set(s);
      n.delete(id);
      return n;
    });
    refresh();
  }

  function toggle(id) {
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }

  async function ask(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    setBusy(true);
    setFocusSrc(null);
    const idx = messages.length;
    const history = messages
      .filter((m) => m.a && m.answered)
      .slice(-3)
      .map((m) => ({ q: m.q, a: m.a }));
    setMessages((m) => [...m, { q, a: "", sources: [], metrics: null, answered: null, verification: null, error: null }]);
    setActive(idx);
    const patch = (fn) => setMessages((m) => m.map((msg, i) => (i === idx ? fn(msg) : msg)));
    try {
      const res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, history, doc_ids: selected.size ? [...selected] : null }),
      });
      if (!res.ok) throw new Error(await errorText(res));
      for await (const { event, data } of sse(res)) {
        if (event === "token") patch((m) => ({ ...m, a: m.a + data }));
        else if (event === "done") patch((m) => ({ ...m, ...data }));
        else if (event === "error") throw new Error(data);
      }
    } catch (err) {
      patch((m) => ({ ...m, error: String(err.message ?? err) }));
    } finally {
      setBusy(false);
    }
  }

  async function runReview() {
    const questions = reviewQs.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 5);
    if (!questions.length || reviewing) return;
    setReviewing(true);
    setGrid(null);
    try {
      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ questions, doc_ids: selected.size ? [...selected] : null }),
      });
      if (!res.ok) throw new Error(await errorText(res));
      setGrid(await res.json());
    } catch (err) {
      setNotice({ kind: "error", text: String(err.message ?? err) });
    } finally {
      setReviewing(false);
    }
  }

  const current = messages[active ?? messages.length - 1];
  const v = current?.verification;

  return (
    <div className="app">
      <header>
        <h1>DocuMind</h1>
        <nav>
          <button className={view === "chat" ? "on" : ""} onClick={() => setView("chat")}>
            Razgovor
          </button>
          <button className={view === "review" ? "on" : ""} onClick={() => setView("review")}>
            Pregled dokumenata
          </button>
        </nav>
        <label className={"upload" + (uploading ? " disabled" : "")}>
          {uploading ? "Učitavam…" : "+ Dodaj dokument"}
          <input ref={fileRef} type="file" accept=".pdf,.txt,.md" onChange={upload} disabled={uploading} hidden />
        </label>
      </header>

      {notice && (
        <div className={"notice " + notice.kind} onClick={() => setNotice(null)}>
          {notice.text}
        </div>
      )}

      <main>
        <section className="chat">
          {docs.length > 0 && (
            <ul className="docs">
              {docs.map((d) => (
                <li key={d.doc_id} className={selected.has(d.doc_id) ? "on" : ""}>
                  <label>
                    <input type="checkbox" checked={selected.has(d.doc_id)} onChange={() => toggle(d.doc_id)} />
                    {d.doc} <span>· {d.pages} str.</span>
                  </label>
                  <button type="button" title="Obriši" onClick={() => remove(d.doc_id)}>
                    ×
                  </button>
                </li>
              ))}
              <li className="hint">{selected.size ? "Samo označeni dokumenti." : "Svi dokumenti."}</li>
            </ul>
          )}

          {view === "chat" ? (
            <>
              {messages.length === 0 && <p className="empty">Učitaj dokument pa postavi pitanje.</p>}
              {messages.map((m, i) => (
                <div key={i} className={"turn" + (i === active ? " active" : "")} onClick={() => setActive(i)}>
                  <p className="q">{m.q}</p>
                  {m.error ? (
                    <p className="a err">Greška: {m.error}</p>
                  ) : (
                    <p className={"a" + (m.answered === false ? " none" : "")}>
                      {m.a ? renderAnswer(m.a, m.verification, (n) => (setActive(i), setFocusSrc(n))) : busy && i === messages.length - 1 ? "…" : ""}
                    </p>
                  )}
                </div>
              ))}
              <div ref={endRef} />
              <form onSubmit={ask}>
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder={docs.length ? "Postavi pitanje o dokumentu…" : "Prvo učitaj dokument"}
                  disabled={busy}
                />
                <button disabled={busy || !question.trim()}>Pošalji</button>
              </form>
            </>
          ) : (
            <div className="review">
              <p className="empty">
                Jedno pitanje po redu (do 5). Svaka ćelija se odgovara iz tog jednog dokumenta.
              </p>
              <textarea
                rows={4}
                value={reviewQs}
                onChange={(e) => setReviewQs(e.target.value)}
                placeholder={"Šta je svrha projekta?\nKoji je stack?"}
              />
              <button onClick={runReview} disabled={reviewing || !reviewQs.trim() || !docs.length}>
                {reviewing ? "Radim…" : "Pokreni pregled"}
              </button>
              {grid && (
                <div className="gridwrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Dokument</th>
                        {grid.questions.map((q) => (
                          <th key={q}>{q}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {grid.rows.map((r) => (
                        <tr key={r.doc_id}>
                          <th>{r.doc}</th>
                          {r.cells.map((c, j) => (
                            <td key={j} className={c.answered ? "" : "none"}>
                              {c.answer}
                              {c.page ? <small> · str. {c.page}</small> : null}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </section>

        <aside>
          <h2>Izvori</h2>
          {v && v.checked > 0 && (
            <p className={"verdict" + (v.unsupported || v.invalid_citations.length ? " warn" : "")}>
              {v.checked - v.unsupported}/{v.checked} tvrdnji potvrđeno izvorom
              {v.invalid_citations.length ? ` · nepostojeći izvor: ${v.invalid_citations.join(", ")}` : ""}
            </p>
          )}
          {current?.sources?.length ? (
            current.sources.map((s) => (
              <article key={s.n} className={focusSrc === s.n ? "focus" : ""} ref={(el) => {
                  if (el && focusSrc === s.n) el.scrollIntoView({ block: "nearest" });
                }}>
                <header>
                  <strong>[{s.n}]</strong> {s.doc} · str. {s.page}
                  <span className="score">{s.score}</span>
                </header>
                <p className={focusSrc === s.n ? "full" : ""}>{highlight(s.text, current.q)}</p>
              </article>
            ))
          ) : (
            <p className="empty">
              {current?.answered === false ? "Nijedan izvor ne odgovara na pitanje." : "Izvori se pojavljuju uz odgovor."}
            </p>
          )}
          {current?.metrics && (
            <dl className="metrics">
              <dt>Pretraga</dt>
              <dd>{current.metrics.retrieval_ms} ms</dd>
              <dt>Prvi token</dt>
              <dd>{current.metrics.first_token_ms} ms</dd>
              <dt>Ukupno</dt>
              <dd>{current.metrics.total_ms} ms</dd>
            </dl>
          )}
        </aside>
      </main>
    </div>
  );
}
