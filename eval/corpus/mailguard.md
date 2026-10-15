# 🛡️ MailGuard

CLI skener Gmail inbox-a za **phishing i fraud mejlove** — proverava da li su mejlovi bezbedni za otvaranje, pre nego što ih otvoriš.

Radi u dva sloja:

1. **Heuristike (lokalno, offline)** — analiza punih email headera i sadržaja:
   - SPF / DKIM / DMARC autentikacija (`Authentication-Results` header)
   - spoofing brenda (display ime „PayPal“ sa levog domena) i lookalike domeni (`paypa1.com`, `bancaintesa-verifikacija.club`)
   - nedoslednosti headera (Reply-To ≠ From, Return-Path ≠ From)
   - maskirani linkovi (tekst prikazuje jedan domen, href vodi na drugi), gole IP adrese, punycode, skraćivači, rizični TLD-ovi, `user@host` trik
   - jezik pritiska/hitnosti (SR + EN) i traženje kredencijala
   - opasni prilozi (`.exe`, `.html`, `.js`, makro dokumenti, arhive)
2. **AI ocena (opciono)** — sumnjivi mejlovi idu na finalnu procenu kroz `claude -p`
   (Claude Code pretplata, **bez API ključa**), sa obrazloženjem i preporukom na srpskom.

Svaki mejl dobija skor 0–100 i presudu: ✅ SIGURAN / ⚠️ SUMNJIV / 🚨 OPASAN.

## Upotreba

```bash
python3 mailguard.py               # poslednjih 10 mejlova iz inbox-a
python3 mailguard.py --last 25     # poslednjih 25
python3 mailguard.py --hours 24    # svi iz poslednja 24h
python3 mailguard.py --mock        # demo na samples/*.eml, bez IMAP-a
python3 mailguard.py --no-ai       # samo heuristike (potpuno offline)
python3 mailguard.py --ai-all      # AI ocena za svaki mejl
python3 mailguard.py --json        # izveštaj kao JSON
```

Izlazni kod: `0` sve sigurno, `1` ima sumnjivih, `2` ima opasnih — zgodno za skriptovanje i automatizaciju.

## Podešavanje

Kopiraj `.env.example` u `.env` i upiši Gmail adresu + [app password](https://myaccount.google.com/apppasswords). Ako `.env` ne postoji, MailGuard automatski koristi `~/automations/inbox-digest/.env` (isti format).

Pristup inbox-u je **strogo read-only** (IMAP `BODY.PEEK`) — ništa se ne označava, ne briše niti menja.

## Automatski dnevni sken (macOS)

`com.uros.mailguard.plist` je launchd agent koji svaki dan u 8:10 skenira poslednja 24h i digne macOS notifikaciju ako nađe sumnjiv ili opasan mejl:

```bash
cp com.uros.mailguard.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.uros.mailguard.plist
```

## Bezbednosne napomene

- Skener nikad ne otvara linkove niti izvršava priloge — analizira samo sirovi tekst poruke.
- Heuristički skor je signal, ne garancija: mejl sa niskim skorom i dalje može biti prevara (npr. kompromitovan legitiman nalog), a marketinški mejlovi umeju da pokupe koji poen. Za granične slučajeve tu je AI sloj.
- Izveštaji se čuvaju u `logs/*.json`.

## Demo

`samples/` sadrži 4 sintetička primera (legitiman LinkedIn, PayPal phishing sa maskiranim linkom na IP adresu, spoofing srpske banke sa opasnim prilogom, newsletter) — `python3 mailguard.py --mock --no-ai` ih sve ispravno klasifikuje.
