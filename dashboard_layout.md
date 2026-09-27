# MetriLLM — Analyse der Dashboard-Struktur

**Ziel:** Nachbau der MetriLLM-Webseite (https://metrillm.dev/) als lokales LLM-Leaderboard auf **Port 8083**.
**Referenz:** https://metrillm.dev/ (SPA, Astro-Build, Supabase-Backend)
**Erstellt:** 2026-09-26

> MetriLLM ist ein Open-Source-Leaderboard für lokale LLM-Performance. Daten kommen von
> Community-Runs (`metrillm` CLI → Supabase). Die Seite ist die visuelle Referenz für
> Nexus-Bench V0.3 (siehe `Konzept_und_Prompt_Anweisungen_fuer_Realisierung.md`).

---

## 1. Seitenstruktur (Routing)

| Route | Inhalt | Anklickbar |
|-------|--------|-----------|
| `/` (Home = Leaderboard) | Haupt-Leaderboard mit Trending, Filtern, Tabelle | **Ja** — Interaktionskern |
| `/my-benchmarks` | Eigene hochgeladene Benchmarks | Ja |
| `/methodology` | Bewertungsmethodik (Scoring, Verdicts) | Ja |
| `/blog` | Blog | Ja |
| `/contributors` | Contributors | Ja |
| `/founding` | Founding / Gründung (cyan-hervorhebung) | Ja |
| `/legal`, `/privacy`, `/terms` | Rechtliches | Ja |
| `https://github.com/MetriLLM/metrillm` | GitHub-Repo (extern) | Ja |

> **Wichtig:** Das Leaderboard ist die **Home-Route `/`**, nicht `/leaderboard`
> (diese liefert „Page Not Found"). Alle Filter/Sortier-Interaktionen laufen auf `/`.

---

## 2. Home-Page `/` — Aufbau (von oben nach unten)

### 2.1 Navigation (Top Bar)
Anklickbare Elemente:
- **Logo** → `/` (Home)
- **Leaderboard** → `/`
- **My Benchmarks** → `/my-benchmarks`
- **Methodology** → `/methodology`
- **Blog** → `/blog`
- **Contributors** → `/contributors`
- **Founding** → `/founding` (aktiv hervorgehoben, cyan)
- **CTA-Button „Get started"** → extern (npm / CLI-Install)
- **CTA-Button „Methodology"** → `/methodology`
- **CTA-Button „Blog"** → `/blog`

### 2.2 Hero-Bereich
- Titel: **„Leaderboard"**
- Subtitle: „Real benchmarks from real hardware. Compare local LLM performance across different setups."
- Install-Command-Block (mit **Copy-Button**):
  ```
  $ npm install -g metrillm@latest
  $ metrillm
  ```
- Hinweis: „Requires Node 20+ and Ollama or LM Studio running"
- Sekundärer Command-Block (mit **Copy-Button**):
  ```
  npx metrillm@latest
  ```

### 2.3 Trending-Panel („Trending — Last 7 days")
- Toggle **„Last 7 days"** (Zeitspanne: 7 Tage)
- **Top Models** — Rangliste 1–5 (anklickbare Model-Namen)
  1. qwen3.8-27b-uncensored-hauhaucs-aggressive-mtp2
  2. prism-ml/bonsai-27b1
  3. google/gemma-4-e4b1
  4. devstral-small-2-24b-instruct-25121
  5. unsloth/qwen3.6-35b-a3b1
- **Top Machines** — Rangliste 1–2 (anklickbare Hardware)
- **Top CPUs** — Rangliste 1–2 (anklickbare CPUs)

### 2.4 Statistik-Leiste
Große Zahlen (animierte Counter):
- **500** total runs
- **286** unique models
- **43** model families
- **51** unique CPUs

### 2.5 Notify-Section
- Text: „Get notified when new models & hardware are benchmarked"
- Eingabe + **„Notify me"** Button

### 2.6 Filter-Bar (13 Filter, alle anklickbar/auswählbar)
| Filter | Optionen |
|--------|----------|
| All families | alle Model-Familien |
| All models | alle Modelle |
| All sizes | alle Größen |
| All quants | alle Quantisierungen |
| All | (Verdict/Status?) |
| All CPUs | alle CPUs |
| All machines | alle Maschinen |
| All architectures | alle Architekturen |
| All OS | alle Betriebssysteme |
| All RAM | alle RAM-Werte |
| All backends | alle Backends (Ollama/LM Studio) |
| All formats | alle Formate (GGUF/MXFP4/etc.) |
| All verdicts | alle Verdicts |

- **Ergebnis-Zähler:** „500 results"
- **Toggle „Best per config"** (Gruppierung auf bestes Modell pro Konfiguration)

### 2.7 Leaderboard-Tabelle — Sortierbare Spalten
Alle Spaltenköpfe sind **anklickbar** (Sortierung asc/desc):

| # | Spalte | Beschreibung |
|---|--------|-------------|
| 1 | **Rank (#)** | Rang |
| 2 | **CPU** | Prozessor |
| 3 | **Model** | Modellname |
| 4 | **Size** | Größe (z.B. `30B/MXFP4`) |
| 5 | **RAM** | Host-RAM (GB) |
| 6 | **Runtime** | Backend (LM STUDIO / OLLAMA) + Format (MLX / GGUF) |
| 7 | **tok/s** | Throughput (sortierbar!) |
| 8 | **TTFT** | Time To First Token |
| 9 | **HW Fit** | Hardware-Fit-Score (0–100) |
| 10 | **Quality** | Quality-Score (0–100) |
| 11 | **Global** | Global-Score (0–100) |
| 12 | **Flags** | Flags (z.B. THINK, ECO, ECOTHINK) |
| 13 | **Verdict** | Endwertung (Excellent/Good/Marginal/Not Recommended) |

- **Pagination:** „12...25" (Seitennavigation)

### 2.8 Footer-Notify
- Text: „Don't miss new benchmarks"
- **„Notify me"** Button

---

## 3. Bewertungsmethodik (`/methodology`) — für Scoring-Logik übernehmen

### 3.1 Global Score
```
Global = 30% × HW-Fit + 70% × Quality
```

### 3.2 Hardware-Fit-Score (0–100)
- **50 %** Speed (tok/s)
- **20 %** TTFT
- **30 %** Memory-Effizienz

### 3.3 Quality-Score (0–100)
- **20 pts** Reasoning
- **20 pts** Coding
- **20 pts** Instruction Following
- **15 pts** Structured Output
- **15 pts** Math
- **10 pts** Multilingual

### 3.4 Hardware-Profile (Schwellenwerte)
| Metric | Entry (≤8 GB) | Balanced (8–32 GB) | High-End (>32 GB) |
|--------|---------------|--------------------|--------------------|
| Speed (excellent) | 20 tok/s | 30 tok/s | 45 tok/s |
| Speed (minimum) | 3 tok/s | 5 tok/s | 6 tok/s |
| TTFT (excellent) | 1.5 s | 1.0 s | 0.7 s |
| TTFT (maximum) | 20 s | 15 s | 12 s |
| Load time max | 4 min | 3 min | 2 min |

### 3.5 Verdict-System (aus Global-Score)
| Verdict | Score | Farbe |
|---------|-------|-------|
| EXCELLENT | ≥ 80 | emerald |
| GOOD | ≥ 60 | cyan |
| MARGINAL | ≥ 40 | amber |
| NOT RECOMMENDED | < 40 | rose |

### 3.6 Disqualifikationsregeln (Score = 0, „NOT RECOMMENDED")
- Unter Mindest-Speed
- TTFT über Maximum
- Load-Time zu lang
- Kritischer RAM-Gebrauch (>90 % RAM-Delta des Modells)

### 3.7 Was gemessen wird
- **Performance (HW Fit):** tok/s, TTFT, RAM-Verbrauch
- **Quality:** Reasoning, Coding, Instruction Following, Structured Output, Math, Multilingual
- **14 Prompts** über **6 Quality-Kategorien** + Hardware-Perf-Messungen

---

## 4. Technische Fakten zum Nachbau

| Aspekt | MetriLLM | Vorschlag Nexus-Bench |
|--------|----------|----------------------|
| Framework | Astro (SPA) | FastAPI + statisches Frontend (analog `bench/dashboard`) |
| Backend | Supabase (Postgres) | SQLite `benchmark_runs` (bestehend) |
| CLI-Erfassung | `npm i -g metrillm` → `metrillm` | Nexus-Bench-Harness |
| Datenquelle | Community-Runs | Lokale Nexus-Nodes |
| Port | 443 (HTTPS) | **8083** |
| Farbschema | Dark, Cyan-Akzent (`#0284c7`), Monospace-Fonts | analog übernehmen |
| Fonts | Chakra Petch (Display), Outfit, JetBrains Mono | analog |

---

## 5. Umsetzungsplan für Port 8083

### 5.1 Pflicht-Funktionen (MVP)
1. **Leaderboard-Tabelle** auf `/` — alle 13 sortierbare Spalten
2. **13 Filter** (Familie/Modell/Größe/Quant/CPU/RAM/Backend/Format/Verdict/…)
3. **Sortierung** asc/desc pro Spalte (Client- oder Server-seitig)
4. **Pagination** (Seitennavigation)
5. **Toggle „Best per config"**
6. **Trending-Panel** (Top Models/Machines/CPUs, 7-Tage-Filter)
7. **Statistik-Leiste** (Runs/Modelle/Familien/CPUs)
8. **Verdict-Farbkodierung** (emerald/cyan/amber/rose)

### 5.2 Datenmodell (SQLite-Abbildung)
Spalten aus MetriLLM → SQLite-Spalten:
`cpu, model_name, size, ram_gb, backend, format, tok_s, ttft_s, hardware_fit, quality, global_score, flags, verdict, family, machine, architecture, os`

### 5.3 Sortierbare Spalten priorisieren
tok/s, TTFT, HW-Fit, Quality, Global — diese 5 sind die Kern-Sortierungen.

### 5.4 Verifikation
- Alle 13 sortierbare Spalten sortieren (asc/desc)
- Alle 13 Filter filtern korrekt
- „Best per config" gruppiert richtig
- Pagination lädt korrekte Seite
- Verdict-Farben stimmen mit Score-Bereich überein

---

## 6. Offene Fragen an Andreas
1. Datenquelle: bestehende `bench/bench.db` (`benchmark_runs`) oder neue MetriLLM-ähnliche Tabelle mit HW-Fit/Quality-Scores?
2. MVP oder vollständiger Nachbau inkl. Trending + Filter + Methodology-Page?
3. Farbschema/Fonts 1:1 übernehmen oder an Nexus-Bench anpassen?
