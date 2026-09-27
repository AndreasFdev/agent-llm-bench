# Agent-LLM-Bench V0.3

## Konzept und Anweisungen für die Realisierung

Stand: 2026-09-27

## 1. Ziele

1. Für Nous Research Hermes-Agenten sollen abhängig vom Einsatzprofil möglichst
	 geeignete lokale Modelle gefunden werden. Das Hauptkriterium ist Qualität;
	 Laufzeit und Ressourcenbedarf sind nachgelagerte, aber sichtbare Kriterien.
2. Zielhardware sind lokale Systeme mit 12–24 GB VRAM und llama.cpp-basierter
	 Inferenz auf den Nexus-Nodes.
3. Die Benchmark-Suite soll ein lokales Dashboard mit Leaderboard und
	 Drill-down von Modell über Experiment und Benchmark bis zum einzelnen Task
	 bereitstellen. Die Bedienidee von https://metrillm.dev/ dient als visuelle
	 Referenz, nicht als technische Abhängigkeit.
4. Ein Quick-Lauf soll normalerweise 20–30 Minuten benötigen. Die harte
	 Obergrenze beträgt 40 Minuten.
5. Ein einzelner Benchmark darf standardmäßig höchstens 300 Sekunden laufen.
	 Ein Timeout muss als Ergebnis gespeichert werden und darf nachfolgende
	 Benchmarks nicht verhindern.
6. Ergebnisse müssen reproduzierbar und nur bei identischer Suite-, Task-,
	 Scorer- und Modellkonfiguration direkt vergleichbar sein.

## 2. Grundentscheidung

Agent-LLM-Bench V0.3 wird als eigenständiges Python-Projekt auf Grundlage
des vorhandenen V0.2-Harnesses weiterentwickelt.

Es wird ausdrücklich **kein Fork von MetriLLM als Projektbasis** erstellt und
das vorhandene Harness wird nicht durch Harbor ersetzt.

Die vorhandenen Besonderheiten sind ein Vorteil und bleiben erhalten:

- Node-1/Node-2/Node-3-Orchestrierung
- Windows- und Linux-Nodes
- automatischer GGUF-Download
- Prüfung vorhandener und beschädigter GGUF-Dateien
- automatische Node-Auswahl
- hierarchische Suche nach optimalen Modellparametern
- llama-swap-Konfiguration und Server-Probes
- Active-Node-Flag und kontrollierter Abbruch
- Speicherung von effektiver Konfiguration und Experimentidentität

Diese Nexus-spezifische Control Plane wird von der eigentlichen
Benchmark-Ausführung getrennt. Dadurch kann der öffentlich nutzbare Teil der
Suite generisch bleiben, ohne die besonderen Clusterfunktionen zu verlieren.

## 3. Bewertung vorhandener Projekte

### 3.1 MetriLLM

MetriLLM ist als Inspiration und optionaler Kurzbenchmark geeignet, aber nicht
als Kern der Agent-LLM-Bench.

Übernehmbare Ideen:

- kurze Performance- und Quality-Messungen
- TTFT- und Tokens-pro-Sekunde-Auswertung
- feste Seeds und reproduzierbare Profile
- konfigurierbare Request-Timeouts
- JSON-/CSV-Export
- übersichtliche Ergebnisdarstellung

Gründe gegen einen MetriLLM-Fork:

- Der öffentliche Code unterstützt primär Ollama und LM Studio.
- Nexus verwendet llama-swap, LiteLLM und OpenAI-kompatible Endpoints.
- Das attraktive Web-Frontend von metrillm.dev ist nicht Bestandteil des
	öffentlichen Repositorys.
- Die 14 Quality-Prompts sind als alleinige Qualitätsbewertung zu schmal.
- Der MetriLLM-Gesamtscore mischt Hardware-Fit und Qualität. Für Nexus sollen
	Capability und Efficiency getrennt sichtbar bleiben.
- Ein TypeScript-Kern würde neben dem bestehenden Python-/Shell-System eine
	zweite technische Plattform einführen.

MetriLLM kann später über einen Adapter als zusätzlicher schneller
Qualitätsanker ausgeführt werden. Die Suite darf davon nicht abhängig sein.

### 3.2 Local-Agent-Benchmark

Das vorhandene Projekt `local-agent-benchmark` ist der beste erste neue
Agentic-Baustein für V0.3.

Vorteile:

- Python-basiert und MIT-lizenziert
- beliebiger OpenAI-kompatibler Endpoint
- 17 strukturierte Agent-Tests
- Tool-Auswahl und Argumentübergabe
- parallele Tool Calls
- Fehler- und Timeoutbehandlung
- Prompt-Injection-Resistenz
- Zustandsänderungen und mehrstufiges Verhalten
- auswählbare Task-IDs
- Task-Level-Ergebnisse
- versionierte Suite

Es wird als gepinnte externe Benchmark-Suite über einen Nexus-Adapter
integriert. Seine eigene Modell- und Docker-Orchestrierung ersetzt nicht das
Nexus-Harness. T-HOP und Swarm werden nicht bei jedem Quick-Lauf ausgeführt,
sondern erhalten eigene Profile.

### 3.3 local_agentic_llm

Das vorhandene Projekt `local_agentic_llm` ist eine wertvolle Task- und
Validatorquelle für:

- Agentic Coding
- Debugging und TDD
- OpenClaw Skills
- Text-to-SQL
- kleine vollständige Softwareaufgaben

Der vorhandene Runner ist stark auf OpenRouter und spezielle API-Wege
ausgerichtet. Deshalb wird er nicht zur Projektbasis. Für V0.3 werden zunächst
3–5 diskriminierende Tasks ausgewählt. Deren Validatoren müssen unabhängig
geprüft und gegen starke sowie schwache Referenzmodelle kalibriert werden.

### 3.4 Harbor und Terminal-Bench

Harbor ist für echte isolierte Agent-Aufgaben, Terminal-Bench, Aider Polyglot
und spätere Deep-Evaluationen geeignet.

Harbor wird nicht Bestandteil der ersten Quick-Suite, weil Container-, Agent-
und Job-Lifecycle zusätzlichen Orchestrierungsaufwand erzeugen und reale
Terminal-Aufgaben die Laufzeitgrenze schnell überschreiten können.

Vorgesehene Verwendung:

- eigenes Profil `deep`
- nur für Modelle, die Quick und Full bestanden haben
- wenige ausgewählte, versionierte Tasks
- optionaler Harbor Viewer für Harbor-eigene Jobs

Der Harbor Viewer ist kein direkter Ersatz für das Nexus-Dashboard, weil er
Harbor-Job-, Trial- und Trajectory-Daten erwartet.

## 4. Zielarchitektur

Die V0.3-Architektur besteht aus fünf getrennten Schichten.

### 4.1 Control Plane

Verantwortlich für:

- Todo-Queue und Modelldeskriptoren
- Node-Registry und Node-Auswahl
- SSH-/PowerShell-Kommunikation
- GGUF-Download und Validierung
- Parameterauflösung
- GPU-Layer- und MTP-Probes
- llama-swap-Konfiguration
- Modellstart und Health-Checks
- Active-Flag und Lifecycle

Die bestehende Logik aus `model_harness.py` wird schrittweise extrahiert, aber
nicht gleichzeitig neu geschrieben. Bis zur nachgewiesenen Parität bleibt der
alte Einstieg als Fassade und Fallback erhalten.

### 4.2 Execution Plane

Ein zentraler Python-Runner führt Suite-Profile und Benchmark-Adapter aus.

Aufgaben:

- Profil und Manifest laden
- Restbudget berechnen
- Benchmark als eigene Prozessgruppe starten
- stdout und stderr erfassen
- Timeout durchsetzen
- bei Timeout vollständigen Prozessbaum beenden
- Rohartefakte sichern
- Adapterparser aufrufen
- kanonisches Resultat speichern
- mit dem nächsten Benchmark fortfahren

Shellskripte dürfen während der Migration weiterhin von Adaptern aufgerufen
werden. Die Lifecycle- und Timeout-Entscheidung liegt jedoch zentral im
Python-Runner.

### 4.3 Benchmark-Adapter

Jeder Adapter beschreibt mindestens:

- eindeutigen Namen
- Adapter- und Benchmark-Version
- Capability-Kategorie
- unterstützte Profile
- verfügbare Task-IDs
- Auswahlstrategie
- Kommando oder Python-Callable
- erwartete Artefakte
- Resultatparser
- Standardtimeout
- Voraussetzungen und Health-Check

Alle Adapter liefern ein einheitliches Ergebnisformat zurück. Externe Projekte
werden nicht mehr direkt aus beliebigen Tier-Skripten angesprochen.

### 4.4 Persistence und Artefakte

SQLite bleibt zunächst die kanonische Datenbank.

In der Datenbank liegen:

- Suite- und Benchmarkidentität
- Modell- und Runtimekonfiguration
- Status und Fehlerklassen
- aggregierte Scores
- Task-Level-Ergebnisse
- relative Artefaktpfade
- Hashes und Versionen

Große Prompts, Antworten, Logs und Rohresultate werden in einem Run-spezifischen
Artefaktverzeichnis gespeichert. SQLite enthält relative Pfade und SHA-256-
Hashes, nicht mehrfach duplizierte große JSON-Blobs.

### 4.5 API und Dashboard

Das vorhandene FastAPI-/SQLite-Dashboard wird weiterverwendet.

Die Drill-down-Hierarchie lautet:

1. Leaderboard
2. Modell
3. Experiment bzw. effektive Konfiguration
4. Suite-Run
5. Benchmark-Run
6. Task-Ergebnis
7. Prompt, Antwort, Validatorausgabe und Fehler

Eine komplette React-Neuentwicklung erfolgt erst, wenn API und Datenmodell
stabil sind. Zunächst wird die vorhandene Oberfläche funktional erweitert.

## 5. Verzeichnisstruktur

Vorgesehene logische Struktur für V0.3:

- `control/` – Nodes, Download, Parameter, Serving und Lifecycle
- `runner/` – Profile, Budget, Prozessausführung und Statusmaschine
- `adapters/` – Nexus-Adapter für externe Benchmarks
- `profiles/` – Smoke-, Quick-, Full-, Deep- und Sweep-Manifeste
- `storage/` – SQLite-Repositories, Migrationen und Artefakte
- `api/` – FastAPI-Endpunkte und Response-Modelle
- `ui/` – Dashboard
- `config/` – öffentliche Beispiele und lokale Konfiguration
- `tests/` – Unit-, Contract- und Integrationstests
- `third_party/` – nur klar gepinnte externe Projekte, falls sie nicht als
	normale Abhängigkeiten installiert werden können

Der bisherige Ordner `/opt/nexus-cluster/bench` bleibt während der Migration
unverändert lauffähig. Externe Repositories werden inventarisiert und erhalten
jeweils URL, Lizenz, Commit-SHA, Änderungsstatus und Verwendungszweck.

## 6. Konfiguration und Veröffentlichbarkeit

Node- und Infrastrukturdaten werden aus dem Python-Code in validierte YAML-
Konfiguration verschoben.

Öffentlich konfigurierbare Felder:

- Node-ID und Alias
- Betriebssystem
- Endpoint und Port
- Probe-Port
- Modellverzeichnis
- llama-server-Pfad
- llama-swap-Konfiguration
- GPU-Zuordnung
- Flash-Attention-Fähigkeit

Nicht versioniert werden:

- produktive IP-Adressen
- SSH-Benutzernamen und Passwörter
- API-Keys
- private LiteLLM-Konfiguration
- private Modell-URLs
- produktive Datenbanken und Ergebnisse
- lokale Diagnose- und Schlüsselinstallationsskripte

Das öffentliche Repository enthält ausschließlich Beispielkonfigurationen und
Dokumentation der benötigten Umgebungsvariablen.

## 7. Timeout- und Budgetkonzept

### 7.1 Benchmark-Timeout

Der Standard beträgt:

- `benchmark_timeout_sec = 300`

Ein Adapter darf nur über sein versioniertes Profil einen abweichenden Wert
erhalten. Versteckte oder intern hartkodierte längere Timeouts sind nicht
zulässig.

Bei Timeout:

1. SIGTERM an die Prozessgruppe senden.
2. Kurze Grace Period abwarten.
3. Verbleibende Prozesse mit SIGKILL beenden.
4. stdout, stderr und vorhandene Teilresultate sichern.
5. Benchmarkstatus auf `timeout` setzen.
6. Mit dem nächsten Adapter fortfahren.

### 7.2 Suite-Budget

Der Quick-Lauf besitzt:

- `suite_budget_sec = 2400`

Vor jedem Adapter wird das Restbudget geprüft. Nach Ablauf werden noch nicht
gestartete Adapter als `budget_exhausted` gespeichert. Der Suite-Status lautet
in diesem Fall `partial`, nicht pauschal `failed`.

### 7.3 Statuswerte

- `queued`
- `running`
- `completed`
- `partial`
- `timeout`
- `failed`
- `skipped`
- `aborted`
- `budget_exhausted`

Infrastrukturfehler wie ein nicht erreichbarer Endpoint, ungültige
Modellkonfiguration oder eine entfernte Active-Node-Flag dürfen den gesamten
Lauf weiterhin kontrolliert beenden.

## 8. Suite-Profile

### 8.1 Smoke

- Zielzeit: 2–5 Minuten
- Endpoint- und Health-Prüfung
- ein kurzer Performance-Test
- wenige Tool-Calling- und Structured-Output-Tasks
- Zweck: fehlerhafte Modelle und Serving-Konfigurationen früh aussortieren

### 8.2 Quick

- Zielzeit: 20–30 Minuten
- harte Grenze: 40 Minuten
- tägliche Modellauswahl und Regression
- eine effektive Runtimekonfiguration
- keine KV-Cache-Matrix
- versionierter, fester Task-Subset

### 8.3 Full

- umfangreiche bestehende Tier-Suite
- keine 30-Minuten-Garantie
- nur für Modelle, die Quick bestanden haben
- größere statistische Stichproben

### 8.4 Deep

- Harbor, Terminal-Bench, Aider Polyglot oder ähnliche Langzeitaufgaben
- nur für Finalisten
- mehrere Stunden sind zulässig
- getrennte Auswertung von Quick und Full

### 8.5 Config-Sweep

- KV-Cache-, Kontext-, MTP-, Draft- und Sampling-Vergleiche
- keine wiederholte vollständige Quality-Suite pro Matrixpunkt
- zuerst billige Probes, danach Bestätigung der Finalisten

## 9. Quick-Suite V1

Die endgültige Taskzahl wird nach instrumentierten Kalibrierläufen festgelegt.
Prozent-Sampling allein ist keine zuverlässige Laufzeitsteuerung.

Vorgesehene Zusammensetzung:

### 9.1 Performance – Budget 4 Minuten

- gekürztes llama-benchy
- TTFT
- Prompt- und Generation-Throughput
- nur die effektive, vom Parameter-Resolver gewählte Konfiguration

### 9.2 Agent-Verhalten – Budget 8 Minuten

- Local-Agent-Benchmark T1–T17 oder kalibrierter repräsentativer Subset
- zunächst ohne T-HOP
- ohne Swarm im normalen Quick-Profil

### 9.3 Tool Calling – Budget 5 Minuten

- BFCL-V4 `simple_python`
- BFCL-V4 `multiple`
- fester deterministischer Subset
- nur eine KV-Konfiguration

### 9.4 Coding – Budget 8 Minuten

- 3–5 kalibrierte Tasks aus `local_agentic_llm`
- alternativ zunächst HumanEval-/LiveCodeBench-Subset
- automatische Validatoren und Sandbox

### 9.5 Instruction Following – Budget 4 Minuten

- kleiner fester IFEval-/IFBench-Subset
- Structured Output und exakte Anweisungsbefolgung

Die Budgets sind Zielwerte. Jeder Adapter unterliegt zusätzlich dem harten
300-Sekunden-Timeout.

## 10. Reproduzierbarkeit

Jeder Suite-Run erzeugt vor dem ersten Benchmark ein unveränderliches Manifest.

Pflichtfelder:

- Schema-Version
- Suite-Level und Suite-Version
- Task-Set-Version
- Task-IDs in Ausführungsreihenfolge
- Hash jedes Prompts und Inputs
- Seed
- Adapter-Versionen
- externe Repository-Commit-SHAs
- Scorer- und Validator-Versionen
- Modellname und GGUF-Hash, soweit verfügbar
- Node und Endpoint-Typ
- effektive llama.cpp-Parameter
- Sampling-, Reasoning-, MTP- und Draft-Konfiguration
- Kontext- und KV-Cache-Konfiguration
- Timeout und Gesamtbudget

Direkte Rangvergleiche sind nur für kompatible Manifest-Versionen zulässig.
Das Dashboard muss inkompatible Runs sichtbar kennzeichnen.

## 11. Datenmodell

`benchmark_runs` bleibt die aggregierte Zeile eines Benchmark-Adapters.

Zusätzliche Metadaten:

- Benchmark-Level
- Benchmark-Version
- Task-Set-Version
- Manifest-Hash
- Seed
- Reproduzierbarkeits-Hash
- Adapterstatus
- Timeoutsekunden
- Capability-Score
- Efficiency-Score

Neue Tabelle `task_results`:

- Task-Result-ID
- Suite-Run-ID
- Benchmark-Run-ID
- Task-ID
- Kategorie
- Status
- Rohscore und normalisierter Score
- Dauer
- TTFT und TPS, falls sinnvoll
- Fehlerklasse und Fehlertext
- Validator-Version
- Prompt-, Antwort- und Log-Artefaktpfad
- Input- und Output-Hash

## 12. Scoring

Es wird keine einzige globale Accuracy direkt aus heterogenen Taskzahlen
berechnet.

Auswertungsebenen:

1. Task-Score
2. normalisierter Benchmark-Score
3. Capability-Gruppenscore
4. getrennte Capability- und Efficiency-Werte
5. optionaler Hermes-Einsatzprofil-Score

Capability-Gruppen:

- Agentic und Tool Use
- Coding und Debugging
- Instruction Following und Structured Output
- Reasoning und Context, soweit im Profil enthalten

Der Efficiency-Score berücksichtigt:

- Gesamtdauer
- erfolgreiche Tasks pro Minute
- TTFT
- Generation-Throughput
- Timeout- und Fehlerquote

Capability und Efficiency werden immer getrennt angezeigt. Ein optionaler
Hermes-Score darf sie gewichten, ersetzt aber nicht die Rohwerte.

## 13. Dashboard-Anforderungen

Pflichtansichten:

- Modell-Leaderboard
- Capability-vs-Efficiency-Pareto
- Modellvergleich bei identischem Manifest
- Konfigurationsvergleich eines Modells
- Experiment- und Suite-Timeline
- Benchmark-Übersicht
- Task-Heatmap
- Timeout- und Fehleranalyse
- Task-Detail mit Prompt, Antwort und Validatorausgabe

Filter:

- Node
- Modellfamilie und Quantisierung
- Kontextgröße
- KV-Cache
- Reasoning und Speculative Decoding
- Suite-Level und Suite-Version
- Benchmark und Capability-Kategorie
- Status

Nur abgeschlossene oder explizit als partiell markierte Experimente dürfen in
Ranglisten erscheinen. Fehlende Werte dürfen nicht still mit Ergebnissen aus
anderen Experimenten ergänzt werden.

## 14. Migrationsphasen

### Phase 0 – V0.2 einfrieren

1. Vollständigen Referenzlauf sichern.
2. DB-Zeilen, Manifest, Logs und Laufzeiten archivieren.
3. Externe Repositories und lokale Änderungen inventarisieren.
4. Secret- und Veröffentlichungs-Audit durchführen.

### Phase 1 – Projektgrenze

1. Entwicklungsbranch `v0.3` anlegen.
2. neue Paketstruktur vorbereiten.
3. Node-Konfiguration auslagern.
4. Control-Plane-Module ohne Verhaltensänderung extrahieren.
5. V0.2-Einstieg als Fassade behalten.

### Phase 2 – Runner

1. kanonisches Adapter- und Resultatformat definieren.
2. Prozessgruppen und Prozessbaum-Kill implementieren.
3. 300-Sekunden-Timeout implementieren.
4. 2.400-Sekunden-Restbudget implementieren.
5. Statusmaschine und Teilresultate implementieren.

### Phase 3 – Quick V1

1. Performance-Adapter integrieren.
2. Local-Agent-Benchmark integrieren.
3. kleinen BFCL-Subset integrieren.
4. Coding-Tasks kalibrieren und integrieren.
5. Instruction-Subset integrieren.
6. reale Laufzeiten messen und Taskzahlen festschreiben.

### Phase 4 – Storage und Dashboard

1. Schema migrieren.
2. Task-Level-Ergebnisse speichern.
3. Artefaktverwaltung implementieren.
4. FastAPI-Endpunkte hierarchisch erweitern.
5. vorhandene UI um Drill-down ergänzen.

### Phase 5 – Validierung und Umschaltung

1. V0.2 und V0.3 mit identischer Konfiguration vergleichen.
2. Quick auf mindestens drei unterschiedlich schnellen Modellen ausführen.
3. jeden Modelllauf mindestens zweimal wiederholen.
4. Flakiness, Rangstabilität und Laufzeit prüfen.
5. erst nach Parität den Standard-Einstieg auf V0.3 umstellen.
6. V0.2 während einer Übergangsphase als Fallback behalten.

## 15. Tests und Abnahmekriterien

Pflichttests:

- Parameterauflösung und Prioritätsreihenfolge
- YAML-Node-Konfigurationsvalidierung
- Linux- und Windows-Pfadbehandlung
- Download-Skip und GGUF-Prüfung
- Prozessbaum-Kill bei Timeout
- Restbudget und `budget_exhausted`
- Statusübergänge
- Manifest- und Reproduzierbarkeits-Hash
- Adapterparser mit gespeicherten Fixtures
- SQLite-Migrationen
- Dashboard-API

Abnahme für Quick V1:

- typische Laufzeit 20–30 Minuten
- harte Grenze 40 Minuten
- kein einzelner Adapter läuft unkontrolliert länger als sein Limit
- Teilresultate bleiben bei Timeout erhalten
- ein Adapterfehler verhindert keine späteren Adapter
- identisches Manifest erzeugt identische Taskauswahl
- zwei Wiederholungen zeigen nachvollziehbare und akzeptable Flakiness
- Drill-down vom Leaderboard bis zum einzelnen Task funktioniert
- Node 1, Node 2 und Node 3 bleiben nutzbar
- Download- und Parameterhierarchie funktionieren unverändert

## 16. Reihenfolge der konkreten Umsetzung

1. V0.2-Referenz und Secret-Audit
2. Konfigurierbare Node-Registry
3. generischer Runner mit Timeout und Budget
4. bestehende Performance-Adapter
5. Local-Agent-Benchmark-Adapter
6. Quick-Manifest und Task-Level-Schema
7. BFCL- und Instruction-Subsets
8. kalibrierte Coding-Tasks
9. Dashboard-Drill-down
10. Full-Profil migrieren
11. Harbor als optionales Deep-Profil evaluieren

### 16.1 Umsetzungsstatus

Stand: 2026-09-27

- [x] GitHub-taugliches Grund-README für `agent-llm-bench-v03` formuliert.
- [x] V0.3-Projektgerüst mit `pyproject.toml`, `src/`, `tests/`, `config/`
	und `docs/` angelegt.
- [x] Öffentliche Beispielkonfiguration `config/nodes.example.yaml`
	erstellt.
- [x] `.gitignore` für lokale Secrets, Datenbanken, Logs und Artefakte
	erstellt.
- [x] Erste Basisdokumente für Architektur, Sicherheitsinventar und
	Third-Party-Inventar erstellt.
- [x] Erste Konfigurationsvalidierung implementiert.
- [x] Fokussierter Testlauf für den Konfigurationsloader erfolgreich.
- [x] Erste typisierte Node-Registry als V0.3-Control-Plane-Baustein
	implementiert und getestet.
- [x] Erste Parameterauflösung als extrahierter, testbarer V0.3-Service
	implementiert und getestet.
- [x] Projekt in `agent-llm-bench-v03` umbenannt: Verzeichnis, Python-Paket
	(`agent_llm_bench_v03`), `pyproject.toml` und alle Doku-Strings.
- [x] Projekt-venv mit `pip install -e ".[dev]"` eingerichtet; kompletter
	Pytest-Lauf grün (34/34).
- [x] V0.2-Harness-Laufpfad repariert: `nexus_bench_v.2/runs` ist wieder ein
	Symlink auf `../runs` (war zu einem leeren Ordner degradiert, dadurch
	ENOENT bei Active-Node-Flags). Einzel-Test gegen eine Node via
	`process_one(path, selected_node="2", move_item=False)`.
- [~] Prompt-0-Inventar erweitert: Architektur-, Sicherheits- und
	Third-Party-Baseline jetzt mit realen lokalen Findings angereichert.
- [x] V0.2-Referenzlauf gestartet: Integrationstest Qwen2.5-Coder-0.5B gegen
	inf-2 (node-2). Symlinks (`runs`, `dashboard`) repariert; Run läuft (2026-09-27).
- [x] V0.2-Harness routet Bench-Suite direkt auf llama-swap (alle Nodes):
	Run-Skripte exportieren `BENCH_BASE=http://<host>:<port>/v1` + `BENCH_KEY=""`
	(node-2 :9292, node-3 :9393, node-1 :9191); `suite_lib.sh` respektiert
	`BENCH_KEY` mit LiteLLM-Fallback. LiteLLM-Proxy :4000 wird nicht mehr
	benötigt — Retry-Kaskaden und 502er bei Proxy-Downtime entfallen.
- [x] Kompatible Control-Plane-Fassade über dem V0.2-`NODES`-Verhalten
	implementiert und getestet (9 Tests: Legacy-Dict-Struktur, Werte, Host-Format,
	Lookup nach ID/Alias/Slot, Endpoint-Format, Nodes-on-Host).
- [~] Download-/Parameter-Extraktion begonnen: Parameterhierarchie migriert,
	Download- und GGUF-Service noch offen.
- [x] Prozessrunner (Prompt 5) implementiert und getestet: alle Tests grün
	(2026-09-27: 34/34 im Gesamt-Pytest-Lauf, inkl. Trunkierungsflag,
	Restbudget-Minimum, budget_exhausted-Block, Abbruchstatus,
	Prozessbaum-Kill).
- [x] Domänenmodell und Adaptervertrag (Prompt 4): Status-Enumeration mit
	Transition-Validierung, TaskResult/BenchmarkResult/SuiteRun/Manifest-Modelle
	mit JSON-Roundtrip, BenchmarkAdapter-Interface mit FakeAdapter, 23 Tests.
- [x] Manifest und Reproduzierbarkeitsidentität (Prompt 7): Deterministische
	Hashes (task_hash, config_hash, reproducibility_hash), Timestamp nicht im
	Hash, Schema-Versionierung, 7 Tests.
- [x] SQLite-Datenbank-Schema V0.3: 12 Tabellen mit Indexes, Storage-Layer mit
	CRUD und Aggregation, 10 Tests.
- [x] Dashboard auf Port 8083 (konfigurierbar): FastAPI + uvicorn, API-Endpunkte
	für Runs, Benchmarks, Leaderboard; HTML-Dashboard mit Status-Anzeige.
- [x] Performance-Adapter (Prompt 8): llama-benchy + TTFT Adapter mit
	Quick/Full-Profilen, Metric-Validierung (NaN/negative/zero abgelehnt),
	Timeout nicht als 0 TPS, 18 Tests. Gesamt: 94/94 Tests grün.
- [x] Local-Agent-Benchmark-Adapter (Prompt 9) — local_agent_adapter.py, T1-T17, 10 Tests
- [x] BFCL- und Instruction-Adapter (Prompt 10) — bfcl_adapter.py, instruction_adapter.py, 14 Tests
- [~] Quick-Profil und Suite-Orchestrierung (Prompt 12) — profiles.py, orchestrator.py (in Arbeit)
- [x] Scoring und Vergleichbarkeit (Prompt 13): Score-Normalisierung (min-max), gewichtete Gesamtwertung, Run-Vergleich mit Deltas, Leaderboard-Ranking — 23 Tests

## 17. Verbindliche Leitlinien für die Realisierung

- Bestehende funktionierende Node-, Download- und Parameterlogik nicht auf
	einmal neu schreiben.
- Kleine, überprüfbare Migrationen mit Regressionstests durchführen.
- Keine externen Benchmarks ungepinnt oder ohne Lizenzdokumentation einbinden.
- Keine produktiven Zugangsdaten oder privaten Resultate veröffentlichen.
- Keine Rankings aus inkompatiblen Manifesten vermischen.
- Timeouts und Fehler nicht als fehlende Daten verstecken.
- Capability und Efficiency getrennt speichern und anzeigen.
- Quick für tägliche Entscheidungen optimieren; Full und Deep bleiben getrennt.
- Ein Task wird nur aufgenommen, wenn Validator und Diskriminationsfähigkeit
	geprüft wurden.
- Neue UI-Technik erst einführen, nachdem API und Datenmodell stabil sind.

## 18. Zusammenfassung

Agent-LLM-Bench V0.3 bleibt ein eigenständiges Projekt. Das vorhandene
Nexus-Harness bildet die Control Plane. Ein neuer Python-Runner übernimmt
Profile, Adapter, harte Zeitbudgets und ein standardisiertes Resultatformat.

Local-Agent-Benchmark wird der erste neue Agentic-Adapter. Aus
`local_agentic_llm` werden ausgewählte Coding-Tasks übernommen. BFCL und
Instruction-Benchmarks bleiben als kleine standardisierte Anker erhalten.
MetriLLM dient als UX- und Methodikinspiration, Harbor später als Deep-Eval-
Erweiterung.

Das vorhandene FastAPI-/SQLite-Dashboard wird zum lokalen Leaderboard mit
vollständigem Task-Drill-down ausgebaut. Damit bleibt die besondere Nexus-
Infrastruktur erhalten, während Benchmark-Ausführung, Reproduzierbarkeit,
Laufzeitkontrolle und Veröffentlichbarkeit deutlich verbessert werden.

## 19. Promptanweisungen für Realisierung

Die folgenden Prompts sind für einen Coding-Agenten bestimmt. Sie werden in
der angegebenen Reihenfolge ausgeführt. Jeder Prompt bildet eine eigenständige,
überprüfbare Arbeitseinheit. Der Agent darf spätere Phasen nicht eigenmächtig
vorziehen.

### 19.1 Gemeinsamer Auftrag für jeden Coding-Agent-Prompt

Der folgende Block wird jedem Einzelprompt vorangestellt:

```text
Du arbeitest an Agent-LLM-Bench V0.3 unter
/opt/nexus-cluster/bench/agent-llm-bench-v03.

Lies zuerst vollständig:
- agent-llm-bench-v03/Konzept_und_Prompt_Anweisungen_fuer_Realisierung.md
- bench/README.md
- die im aktuellen Prompt genannten Quelldateien

Verbindliche Regeln:
1. V0.2 unter /opt/nexus-cluster/bench muss bis zur ausdrücklich freigegebenen
	Umschaltung unverändert lauffähig bleiben.
2. Verändere keine produktive llama-swap-Konfiguration, starte keine langen
	Benchmarks und lade keine Modelle herunter, sofern der aktuelle Prompt dies
	nicht ausdrücklich verlangt.
3. Untersuche vor Änderungen den realen Datenfluss. Erfinde keine
	Funktionssignaturen, Tabellen oder Ergebnisformate.
4. Arbeite testgetrieben: erst reproduzierbarer fehlender Test oder messbare
	Baseline, danach kleinste korrekte Implementierung.
5. Übernimm keine produktiven IPs, Benutzernamen, Passwörter, API-Keys,
	Modell-URLs, Datenbanken oder privaten Resultate in versionierbare Dateien.
6. Verändere externe Projekte nicht ungekennzeichnet. Nexus-spezifische Logik
	gehört in Adapter.
7. Öffentliche APIs und V0.2-Verhalten bleiben erhalten, sofern der Prompt
	keine explizite Migration verlangt.
8. Keine stillen Fehler: Status, Timeout, Skip, Missing und Teilresultate
	müssen explizit gespeichert und geloggt werden.
9. Führe nach jeder Änderung gezielte Tests und danach den relevanten größeren
	Testsatz aus. Keine Erfolgsmeldung ohne frische Testausgabe.
10. Dokumentiere geänderte Dateien, Entscheidungen, Tests, bekannte Grenzen
	 und den nächsten freigegebenen Schritt.

Stop-Regel:
- Implementiere ausschließlich den aktuellen Prompt.
- Fehlt eine Voraussetzung, dokumentiere den Blocker präzise und stoppe.
- Beginne den nächsten Prompt erst nach Abnahme dieses Schritts.
```

### 19.2 Prompt 0 – Bestand, Baseline und Sicherheitsinventar

```text
Ziel:
Schaffe eine belastbare Ausgangsbasis für V0.3, ohne Produktionsverhalten zu
ändern.

Untersuche mindestens:
- /opt/nexus-cluster/bench/model_harness.py
- /opt/nexus-cluster/bench/suite_lib.sh
- /opt/nexus-cluster/bench/run_nexus_suite_tier1.sh
- /opt/nexus-cluster/bench/run_nexus_suite_tier2.sh
- /opt/nexus-cluster/bench/run_nexus_suite_tier3.sh
- /opt/nexus-cluster/bench/schema_v2.sql
- /opt/nexus-cluster/bench/dashboard/
- /opt/nexus-cluster/bench/local-agent-benchmark/
- /opt/nexus-cluster/bench/local_agentic_llm/

Arbeitsauftrag:
1. Ermittle den realen Datenfluss vom Todo-Eintrag bis zum Dashboard.
	Dokumentiere Funktionen, Prozesse, Dateien, Datenbankwrites und Fehlerpfade.
2. Erfasse alle Node-spezifischen Werte und klassifiziere sie als öffentlich
	konfigurierbar, lokal privat oder Secret.
3. Suche nach hartkodierten Hosts, Benutzernamen, Passwörtern, Tokens,
	Schlüsseln, Modell-URLs und absoluten Infrastrukturpfaden. Gib gefundene
	Secret-Werte niemals in Logs oder Dokumentation aus.
4. Inventarisiere externe Repositories mit Name, Pfad, Upstream-URL, Lizenz,
	Commit-SHA, lokalen Änderungen und Status active/experimental/archive.
5. Ermittle alle vorhandenen Timeouts und unbeschränkten Subprozesse.
6. Ermittle das reale SQLite-Schema aus Schema-Dateien und DB-Metadaten, ohne
	produktive Daten zu verändern.
7. Lege unter agent-llm-bench-v03/docs eine Architektur-Baseline, ein
	bereinigtes Sicherheitsinventar und ein Third-Party-Inventar an.
8. Ergänze eine .gitignore für lokale Konfiguration, Datenbanken, Resultate,
	Logs, Artefakte, virtuelle Umgebungen und Secrets.

Tests und Nachweise:
- Python- und Shell-Syntax der aktiven Einstiegspunkte prüfen.
- Vorhandene Tests unverändert ausführen und Ergebnisse als Baseline erfassen.
- Nachweisen, dass keine produktive Datei verändert wurde.
- Nachweisen, dass neue Dokumente keine erkannten Secret-Werte enthalten.

Abnahme:
- Datenfluss und Refactor-Schnittstellen sind vollständig dokumentiert.
- Externe Repositories sind revisionsgenau inventarisiert.
- Alle unbeschränkten Benchmarkprozesse sind bekannt.
- V0.2 besitzt denselben Teststatus wie vor diesem Schritt.

Nicht umsetzen:
- keine Module extrahieren
- kein Datenbankschema ändern
- keine Benchmarkausführung ändern
- keine produktiven Secrets automatisch verschieben
```

### 19.3 Prompt 1 – Projektgerüst und öffentliche Konfiguration

```text
Ziel:
Erzeuge ein installierbares, testbares Python-Projekt für V0.3 und eine
validierte Konfiguration, ohne V0.2 umzuschalten.

Arbeitsauftrag:
1. Lege eine Python-Paketstruktur unter agent-llm-bench-v03 mit control,
	runner, adapters, profiles, storage, api und tests an.
2. Erstelle pyproject.toml mit minimalen Runtime- und Development-
	Abhängigkeiten.
3. Definiere typisierte Konfigurationsmodelle für globale Pfade, Nodes,
	Endpoint, Serving und Runtime-Defaults.
4. Erstelle config/nodes.example.yaml mit ausschließlich neutralen Werten.
5. Lokale Konfiguration wird über Umgebungsvariable oder ignorierte Datei
	gewählt. Kein stiller Fallback auf produktive Nexus-Werte.
6. Implementiere klare Validierungsfehler für fehlende Felder, ungültige OS-
	Werte, doppelte IDs/Aliase, ungültige Ports und widersprüchliche Pfade.
7. Dokumentiere Installation, Konfigurationsauflösung und Secret-Handhabung im
	README.

Tests:
- gültige Linux- und Windows-Nodes
- mehrere Nodes auf demselben Host mit verschiedenen GPUs und Ports
- doppelte Node-ID und doppelter Alias
- doppelter Serving-Port auf demselben Host
- ungültiger Port, fehlender Pflichtwert und unbekanntes Betriebssystem
- keine unbeabsichtigte Übernahme produktiver Defaults

Abnahme:
- Paket installiert sich in einer frischen virtuellen Umgebung.
- Konfiguration lädt ohne Verbindung zu produktiven Nodes.
- Fehler nennen Feld und Ursache.
- Neue versionierbare Dateien enthalten keine produktiven Werte.

Nicht umsetzen:
- model_harness.py noch nicht umstellen
- keine SSH-Verbindung, Downloads oder Serverstarts
```

### 19.4 Prompt 2 – Node-Registry und Control-Plane-Fassade

```text
Ziel:
Kapsle Node-Zugriff und Node-Auswahl hinter testbaren Schnittstellen, ohne das
beobachtbare V0.2-Verhalten zu ändern.

Arbeitsauftrag:
1. Analysiere alle realen Verwendungen von NODES und abgeleiteten Konstanten
	in model_harness.py.
2. Implementiere eine NodeRegistry mit Lookup nach ID, Alias, Host/Port und
	GPU-Zuordnung.
3. Implementiere OS-spezifische Pfad- und Kommandoabstraktionen für Linux und
	Windows. Keine unsichere Shellstring-Konkatenation.
4. Implementiere eine schmale Fassade, die aus V0.3-Konfiguration dieselben
	Werte wie das bisherige NODES-Dictionary liefert.
5. Schreibe Charakterisierungstests für bisherige Node-Auswahl und Pfade.
6. Ändere model_harness.py nur minimal und nur bei nachgewiesener Parität.

Tests:
- Lookup und Fehler bei unbekannter Node
- Alias-Eindeutigkeit
- Linux- und Windows-Modellpfade
- Quoting problematischer Modellnamen
- Node-Auswahl bei gefälschten belegten und freien Zuständen
- identische Legacy-Ausgaben für bekannte Fixtures

Abnahme:
- Node-Entscheidungen sind ohne echte SSH-Verbindung testbar.
- Keine neue Funktion kennt hartkodiert Node 1, 2 oder 3.
- V0.2-Tests bleiben grün.

Nicht umsetzen:
- keine echte SSH-Schicht ersetzen
- keine Parameterauflösung ändern
- keine Benchmarkadapter implementieren
```

### 19.5 Prompt 3 – Download-, GGUF- und Parameterdienste

```text
Ziel:
Extrahiere Download-, GGUF-Prüf- und Parameterlogik in isolierte Dienste bei
vollständiger Verhaltensparität.

Arbeitsauftrag:
1. Identifiziere Funktionen und Seiteneffekte für URL-Auswahl, Remotezustand,
	Download, Retry, GGUF-Magic-Prüfung, vorhandene Datei und Eskalation.
2. Erstelle einen ModelArtifactService mit injizierbarem RemoteExecutor und
	Dateisystem. Tests dürfen nicht per SSH zugreifen.
3. Charakterisiere die reale Parameterpriorität: parms_optimal, parms, tuned,
	exaktes Modell, Modellfamilie und Fallback.
4. Erstelle einen ParameterResolver, dessen Resultat effektive Parameter,
	Quelle, Priorität, Warnungen und Hash enthält.
5. Bewahre Parsingformate und Semantik. Ungültige Werte werden explizit
	diagnostiziert.
6. Biete kompatible Fassaden für schrittweise Nutzung durch model_harness.py.

Tests:
- Download-Skip bei gültigem GGUF
- erneuter Download bei ungültiger/unvollständiger Datei
- URL-/Dateinamenauflösung, Retry und Fehlerklassifikation
- Linux-/Windows-Kommandogenerierung
- vollständige Parameterprioritätsmatrix
- bisher unterstützte JSON-/Markdown-Formate
- ungültige parms_optimal-Datei, Familienfallback und stabiler Hash

Abnahme:
- Characterization Fixtures ergeben identische effektive Parameter.
- Tests benötigen weder Netzwerk noch produktive Modellfiles.
- Jeder Parameterwert besitzt eine nachvollziehbare Quelle.

Nicht umsetzen:
- Parameteroptimierung nicht neu entwerfen
- keine realen Downloads oder Serving-Änderungen
```

### 19.6 Prompt 4 – Domänenmodell und Adaptervertrag

```text
Ziel:
Definiere den stabilen Vertrag zwischen Suite-Runner, Adaptern und Storage.

Arbeitsauftrag:
1. Definiere typisierte Modelle für SuiteProfile, SuiteRun, BenchmarkSpec,
	BenchmarkRun, TaskSelection, TaskResult, ArtifactRef und FailureInfo.
2. Implementiere Statuswerte queued, running, completed, partial, timeout,
	failed, skipped, aborted und budget_exhausted als Enumeration.
3. Definiere erlaubte Statusübergänge und blockiere ungültige Übergänge.
4. Definiere BenchmarkAdapter mit prepare, validate, execute und parse.
5. Definiere ein kanonisches, versioniertes JSON-Schema für Resultate.
6. Trenne Rohscore, normalisierten Score, Capability und Performance. Fehlende
	Werte dürfen nicht als Nullleistung interpretiert werden.
7. Implementiere Serialisierung, Roundtrip und Fehler bei inkompatibler
	Schema-Version.

Tests:
- gültige/ungültige Statusübergänge
- vollständiger JSON-Roundtrip
- unbekannte Schema-Version
- Timeout mit und ohne Teilresultate
- mehrere TaskResult-Einträge und optionale Performancewerte
- ArtifactRef mit relativem Pfad und SHA-256

Abnahme:
- Ein FakeAdapter läuft ohne SQLite und Subprozess vollständig durch.
- Modelle enthalten keine benchmark-spezifischen Sonderfelder.
- Vertrag und JSON-Beispiel sind dokumentiert.

Nicht umsetzen:
- kein realer Adapter, keine SQLite-Migration, kein Dashboard
```

### 19.7 Prompt 5 – ProcessRunner, Timeout und Gesamtbudget

```text
Ziel:
Implementiere robuste Prozessausführung und beweise Timeout- und
Budgetverhalten automatisiert.

Arbeitsauftrag:
1. Schreibe zuerst Hilfsprozesstests für Erfolg, Fehler, stdout/stderr, Hängen
	und Kindprozesse.
2. Implementiere ProcessRunner mit eigener Prozessgruppe/Session.
3. Standardtimeout ist 300 Sekunden, in Tests auf kurze Werte konfigurierbar.
4. Bei Timeout: kontrolliert terminieren, Grace Period, danach gesamten
	verbleibenden Prozessbaum hart beenden.
5. Erfasse Start, Ende, Dauer, Exitcode, Timeout, stdout, stderr und
	Trunkierungsstatus. Große Ausgaben als Artefakt streamen.
6. Implementiere SuiteBudget mit 2400 Sekunden und injizierbarer monotonic
	clock.
7. Effektiver Timeout ist das Minimum aus Adaptertimeout und Restbudget.
8. Nach Budgetende keine neuen Prozesse starten.
9. Abbruchsignal und Active-Flag müssen kontrolliert berücksichtigt werden.

Tests:
- Erfolg und Exitcode ungleich null
- Timeout, Kindprozess-Kill und SIGKILL nach ignoriertem SIGTERM
- stdout/stderr bleiben bei Timeout erhalten
- große Ausgabe wird begrenzt und gesichert
- Restbudget kleiner als Adaptertimeout
- budget_exhausted verhindert nächsten Start
- Abbruch ergibt aborted statt timeout
- nach Timeout wird ein weiterer Adapter ausgeführt

Abnahme:
- Kein Test hinterlässt verwaiste Prozesse.
- Timeouttests laufen in Sekunden.
- ProcessRunner enthält keine benchmark-spezifische Logik.

Nicht umsetzen:
- keinen produktiven Benchmark starten
- Shell-timeout nicht als einzige Schutzschicht verwenden
```

### 19.8 Prompt 6 – SQLite-Migration und Artefaktspeicher

```text
Ziel:
Erweitere das Datenmodell migrationssicher um V0.3-Metadaten und Taskdetails,
ohne bestehende Resultate zu verlieren.

Arbeitsauftrag:
1. Vergleiche schema_v2.sql, die reale SQLite-Struktur und alle Writer.
	Dokumentiere Abweichungen vor jeder Änderung.
2. Entwirf versionierte, idempotente Migrationen. Keine manuelle Änderung der
	produktiven Datenbank während der Entwicklung.
3. Ergänze benchmark_runs nur um notwendige V0.3-Aggregatfelder.
4. Erstelle task_results mit Fremdschlüsseln, Status, Scores, Dauer,
	Fehlerdaten, Validatorversion sowie Input-/Output-Hashes.
5. Erstelle Artefaktreferenzen für relativen Pfad, MIME-Typ, Größe und SHA-256.
6. Implementiere Repository-Klassen mit Transaktionen. Benchmarkaggregat und
	Taskresultate müssen atomar gespeichert werden.
7. Implementiere Idempotenzschlüssel gegen doppelte Runs und Tasks.
8. Bestehende V0.2-Writer bleiben während der Migration funktionsfähig.

Tests:
- Migration einer leeren V0.2-Datenbank
- Migration einer Fixture-DB mit Legacy-Runs
- Migration zweimal ausführen
- Rollback bei absichtlichem Fehler
- Fremdschlüssel und Löschverhalten
- atomarer Benchmark-/Task-Write
- Idempotenz bei Wiederholung
- Artefaktpfad darf das Root nicht verlassen
- Hashprüfung eines Artefakts

Abnahme:
- V0.2-Zeilen bleiben unverändert lesbar.
- Migration ist wiederholbar und versioniert.
- Backup-/Restore-Anweisung ist dokumentiert.
- Große Inhalte werden nicht mehrfach in SQLite dupliziert.

Nicht umsetzen:
- keine produktive Datenbank migrieren
- noch keine Dashboardansicht erstellen
```

### 19.9 Prompt 7 – Manifest und Reproduzierbarkeitsidentität

```text
Ziel:
Erzeuge vor jedem Lauf ein unveränderliches Manifest und verhindere
unzulässige Ergebnisvergleiche.

Arbeitsauftrag:
1. Definiere Manifest Schema V1 mit allen Pflichtfeldern aus Abschnitt 10.
2. Normalisiere deterministisch: sortierte Schlüssel, definierte Zahlen- und
	Bool-Darstellung, UTF-8 und keine flüchtigen Werte im Vergleichshash.
3. Trenne run_id/started_at vom reproduzierbaren Manifestinhalt.
4. Definiere task_manifest_hash, config_hash und reproducibility_hash mit klar
	dokumentierter Bedeutung.
5. Taskauswahl muss vor dem ersten Adapter feststehen.
6. Implementiere Vergleichbarkeit: direkt, eingeschränkt oder inkompatibel,
	jeweils mit maschinenlesbaren Gründen.
7. Prüfe Hashes von Prompt-, Dataset- und Scorerdateien.
8. Schreibe das Manifest atomar vor Adapterstart und ändere es danach nicht.

Tests:
- andere Key-Reihenfolge ergibt gleichen Hash
- andere Taskreihenfolge verändert Task-Manifest-Hash
- Timestamp verändert Reproduzierbarkeitshash nicht
- Modellparameter verändern config_hash
- Scorerversion verändert reproducibility_hash
- beschädigtes Artefakt wird erkannt
- Kompatibilitätsgründe sind deterministisch
- abgebrochener Write hinterlässt kein gültiges Teilmanifest

Abnahme:
- Zwei identische Fixtures erzeugen identische Hashes.
- Storage und Dashboard können Vergleichbarkeit ohne raw_json bestimmen.
- Schema und Hashformeln sind dokumentiert.

Nicht umsetzen:
- keine echten Task-Subsets auswählen
- noch keine Scores berechnen
```

### 19.10 Prompt 8 – Performance-Adapter

```text
Ziel:
Integriere gekürztes llama-benchy und TTFT als erste reale Adapter.

Arbeitsauftrag:
1. Analysiere llama_benchy_run und ttft_run einschließlich Eingaben,
	Artefakten, DB-Writes und Fehlerfällen.
2. Erstelle getrennte oder nachvollziehbar kombinierte Performance-Adapter.
3. Nutze ausschließlich die effektive Konfiguration des Modellruns. Keine
	KV-Matrix im Quick-Profil.
4. Quick muss in vier Minuten Zielbudget passen. Reduziere Warmups oder
	Messpunkte nur über sichtbar versionierte Profile.
5. Parser weisen fehlende, ungültige, NaN-, null- oder negative Messwerte ab.
6. Speichere PP/TG-Throughput, TTFT, Messanzahl, gültige Messungen, Kontext und
	Rohartefakte.
7. V0.2-Funktionen bleiben unverändert nutzbar.

Tests:
- gültige und ungültige llama-benchy-Fixtures
- TTFT mit gültigem Stream und Stream ohne Token
- HTTP-Fehler und Stall
- Timeout wird nicht als 0 TPS gespeichert
- kanonisches Resultat und DB-Roundtrip
- Fake-Endpoint-Integration ohne reales Modell

Abnahme:
- Adapter läuft über ProcessRunner und SuiteBudget.
- Keine direkte DB-Schreiblogik liegt im Adapterprozess.
- Quick- und Full-Parameter sind sichtbar versioniert.

Nicht umsetzen:
- keine KV-Matrix
- keine produktiven llama-server-Parameter ändern
```

### 19.11 Prompt 9 – Local-Agent-Benchmark-Adapter

```text
Ziel:
Integriere Local-Agent-Benchmark als primäre Agentic-Komponente von Quick.

Arbeitsauftrag:
1. Lies README, Lizenz, tests/harness.py, tests/tests.py, tests/tools.py,
	scripts/summarize.py und reale Resultatbeispiele vollständig.
2. Ermittle Commit-SHA und lokale Abweichungen zum Upstream.
3. Nexus-spezifische Endpoint-, Task- und Outputlogik gehört in den Adapter,
	nicht in ungekennzeichnete Upstream-Änderungen.
4. Übergib BENCH_BASE_URL und BENCH_API_KEY über die Prozessumgebung. Secrets
	dürfen weder im Kommando noch in Logs erscheinen.
5. Wähle zunächst T1–T17 ohne T-HOP und Swarm. Liegt die reale Dauer über acht
	Minuten, definiere einen festen, begründeten Subset.
6. Äußeres Limit ist 300 Sekunden. Interne Request-Timeouts dürfen es nicht
	aushebeln.
7. Parse je Task Pass/Fail, Grund, Tool Calls, Latenz und TPS.
8. Übernimm suite_version und Taskdefinition-Hashes ins Manifest.

Tests:
- Parser gegen reale results.json-Fixtures
- Pass, Fail, Human-Review und fehlendes Resultat
- unbekannte Suite-Version
- Endpoint/API-Key ohne Secret-Leak
- äußerer Timeout mit Teilresultaten
- DB-Roundtrip aller TaskResult-Einträge
- Fake OpenAI-Endpoint für mindestens zwei Tests

Abnahme:
- Ein Adapteraufruf erzeugt Aggregat und Taskdetails.
- T-HOP/Swarm sind getrennt konfigurierbar und in Quick deaktiviert.
- Upstream bleibt sauber oder Änderungen sind dokumentiert.
- reale Dauer und Flakiness eines Kalibrierlaufs sind dokumentiert.

Nicht umsetzen:
- keine Live-Tools im reproduzierbaren Quick-Profil
- kein Concurrency-Sweep in Quick
```

### 19.12 Prompt 10 – BFCL- und Instruction-Adapter

```text
Ziel:
Integriere feste Vergleichsanker für Tool Calling und Instruction Following.

Arbeitsauftrag:
1. Analysiere aktuelle BFCL-, IFEval- und IFBench-Aufrufe, Writer,
	Resultatdateien und Scorer.
2. Definiere einen festen BFCL-V4-Subset aus simple_python und multiple. Alle
	Task-IDs stehen vor Runstart im Manifest.
3. Führe BFCL in Quick nur mit der effektiven KV-Konfiguration aus.
4. Definiere einen festen IFEval-/IFBench-Subset für Instruction Following und
	Structured Output.
5. Auswahl muss repräsentativ, deterministisch und dokumentiert sein. Nicht
	nur einfache Aufgaben auswählen.
6. Protokolliere Generation und Scoring unterscheidbar, liefere jedoch ein
	gemeinsames kanonisches Benchmarkresultat.
7. Klassifiziere Scorerfehler, fehlende Antworten und Parserfehler getrennt.
8. BFCL hat fünf Minuten, Instruction vier Minuten Zielbudget; äußeres Limit
	jeweils höchstens 300 Sekunden.

Tests:
- deterministische Auswahl und Hashänderung bei geändertem Subset
- vollständige und partielle BFCL-Fixtures
- fehlende versus falsche Antwort
- Scorerfehler versus Modellfehler
- IFEval-/IFBench-Fixtures
- Timeout nach Generation mit Teilresultaten
- DB- und Manifest-Roundtrip

Abnahme:
- Subsets und Begründung sind dokumentiert.
- Keine KV-Matrix in Quick.
- Alle Task-IDs stehen in Manifest und task_results.
- Full-Ausführung bleibt verfügbar.

Nicht umsetzen:
- offizielle Scorerlogik nicht verändern
- keine Vollsuite als Quick deklarieren
```

### 19.13 Prompt 11 – Coding-Task-Kalibrierung und Adapter

```text
Ziel:
Wähle 3–5 belastbare lokale Coding-Tasks und integriere sie reproduzierbar.

Arbeitsauftrag:
1. Inventarisiere Tasks, Abhängigkeiten, Sandboxbedarf, Validatorlogik,
	typische Tokens und bekannte Validatorprobleme in local_agentic_llm.
2. Wähle komplementäre Fähigkeiten: Bugfix, TDD, kleine Implementierung,
	Dateioperationen und optional Text-to-SQL.
3. Prüfe jeden Validator mit korrekter, leerer, offensichtlich falscher und
	nur oberflächlich plausibler Lösung.
4. Validatoränderungen werden versioniert und ihre Vergleichsauswirkung
	dokumentiert.
5. Führe Tasks in isolierten temporären Workspaces ohne Standard-Netzwerk aus.
6. Begrenze Kommandos, Dateipfade und Ressourcen; kein Workspace-Ausbruch.
7. Parse Validatorchecks einzeln in TaskResult.
8. Coding-Zielbudget ist acht Minuten, äußeres Adapterlimit 300 Sekunden. Falls
	nötig, splitte klar oder reduziere den festen Subset.

Tests:
- Validator-Sanity-Cases
- Workspace-Isolation und Path-Traversal-Abwehr
- Netzwerkgrenze, sofern vorgesehen
- Validator-Timeout und Cleanup
- Parser und DB-Roundtrip
- unveränderte Taskfixtures

Abnahme:
- Jeder Task unterscheidet korrekte von trivial/falsch erzeugten Lösungen.
- Validatorversion und Taskhash stehen im Manifest.
- Auswahl und Ausschlüsse sind begründet.
- Keine OpenRouter-Abhängigkeit im Nexus-Adapter.

Nicht umsetzen:
- keine unkalibrierten Tasks in Quick
- keine manuelle Nachbewertung als regulären Scorepfad
```

### 19.14 Prompt 12 – Quick-Profil und Suite-Orchestrierung

```text
Ziel:
Verbinde fertige Adapter zu einer Quick-Suite mit 20–30 Minuten Zielzeit und
40 Minuten harter Grenze.

Arbeitsauftrag:
1. Definiere Quick V1 mit Adapterreihenfolge, Taskauswahl, Einzelbudgets,
	Timeout und Gesamtbudget.
2. Reihenfolge: Smoke, Performance, Local-Agent, BFCL, Coding, Instruction.
3. Erzeuge Manifest und Suite-Run vor dem ersten Adapter.
4. Aktualisiere Status atomar nach jedem Adapter.
5. Benchmarktimeout/-fehler ergibt partial und die Suite läuft weiter.
	Infrastrukturfehler oder Active-Flag beenden kontrolliert.
6. Restbudget entscheidet vor jedem Start; übrige Adapter erhalten
	budget_exhausted.
7. Implementiere Dry-Run ohne Prozesse und DB-Seiteneffekte.
8. Resume ist nur bei identischem Manifest und effektiver Konfiguration
	erlaubt. Persistierte Adapter nicht doppelt ausführen.
9. Aggregiere Capability-Gruppen, aber noch keinen undurchsichtigen Globalscore.

Tests:
- vollständig erfolgreicher Fake-Run
- Timeout/Fehler, danach erfolgreicher Adapter
- Infrastrukturfehler und Active-Flag-Abbruch
- Gesamtbudget erschöpft
- Dry-Run ohne Seiteneffekte
- Resume, Idempotenz und Ablehnung inkompatiblen Resume
- Status/Artefakte nach simuliertem Prozessabsturz

Abnahme:
- Alle Fehlerpfade besitzen vollständige Statuswerte.
- Keine verwaisten Prozesse oder scheinbar gültigen Teilmanifeste.
- Dry-Run zeigt konsistente Budgets.
- Quick läuft gegen Fake-Endpoint vollständig in CI.

Nicht umsetzen:
- keine produktive Standardumschaltung
- kein Harbor-/Deep-Profil
```

### 19.15 Prompt 13 – Scoring und Vergleichbarkeit

```text
Ziel:
Implementiere transparente Capability-, Efficiency- und optionale
Hermes-Profil-Scores ohne inkompatible Runs zu vermischen.

Arbeitsauftrag:
1. Dokumentiere je Benchmark Rohscore, Normalisierung und Richtung
	besser/schlechter.
2. Berechne zuerst Benchmarkscore, danach Capability-Gruppenscore. Gewichte
	Benchmarks statt einzelner Taskzeilen, damit große Sets nicht dominieren.
3. Berechne Efficiency separat aus erfolgreichen Tasks pro Zeit, TTFT,
	Throughput und Timeout-/Fehlerquote. Fehlende Werte explizit behandeln.
4. Implementiere optionale, konfigurierbare Hermes-Profile wie agentic,
	coding und balanced. Gewichte und Scoreversion müssen sichtbar sein.
5. Rangvergleiche nur kompatible Manifeste. Inkompatible Runs dürfen
	nebeneinander stehen, aber nicht dieselbe Rangliste bilden.
6. Verwende keine MetriLLM-artige Hardware-Tier-Normalisierung. Hardware und
	Node bleiben Kontext- und Filterfelder.
7. Speichere alle Scorekomponenten nachvollziehbar.

Tests:
- mehr Tasks erzeugen nicht automatisch mehr Gewicht
- fehlender Performancewert
- Timeout verschlechtert Efficiency transparent
- partielle Suite ist gekennzeichnet
- identische Eingaben ergeben identische Scores
- neue Scoreversion macht Runs inkompatibel
- Grenzwerte und Division durch null
- Golden Fixtures mit manuell berechneten Erwartungen

Abnahme:
- Jede Rangzahl ist aus gespeicherten Komponenten rekonstruierbar.
- Capability und Efficiency bleiben getrennte Primärwerte.
- Formeln, Gewichte und Versionierung sind dokumentiert.

Nicht umsetzen:
- keine undokumentierten Gewichte
- keine Vermischung von Quick, Full und Deep
```

### 19.16 Prompt 14 – Dashboard-API und Drill-down

```text
Ziel:
Erweitere das vorhandene FastAPI-/SQLite-Dashboard um die V0.3-Hierarchie,
ohne sofort einen vollständigen Frontend-Neubau zu beginnen.

Arbeitsauftrag:
1. Analysiere alle Endpunkte und SQL-Abfragen in dashboard/server.py sowie die
	Nutzung in dashboard/index.html.
2. Definiere stabile Response-Modelle für Leaderboard, Modelle, Experimente,
	Suite-Runs, Benchmark-Runs, Task-Results und Artefakte.
3. Verhindere N+1-Abfragen und ungefiltertes Laden großer Rohdaten.
4. Ergänze API-Endpunkte entlang der vollständigen Drill-down-Hierarchie.
5. Implementiere Filter für Manifestkompatibilität, Status, Node, Kontext,
	KV-Cache, Capability, Suite-Level und Version.
6. Erweitere die vorhandene Oberfläche klickbar:
	Leaderboard -> Modell -> Experiment -> Suite -> Benchmark -> Task.
7. Zeige timeout, partial, missing, invalid und budget_exhausted sichtbar an.
8. Ergänze Quality-vs-Time-Pareto, Task-Heatmap und Fehlerübersicht.
9. Artefakte dürfen nur aus dem konfigurierten Root gelesen werden. Verhindere
	Path Traversal und behandle unbekannte MIME-Typen sicher.
10. Legacy-V0.2-Runs bleiben lesbar und erhalten einen Legacy-Hinweis.

Tests:
- API-Tests mit Fixture-Datenbank und leerer Datenbank
- Legacy- und V0.3-Runs gemeinsam
- inkompatible Manifeste und Filterkombinationen
- Pagination und große Ergebnismengen
- Artefakt-Path-Traversal
- keine Secrets in API-Responses
- Frontend-Smoke-Test für die Navigation

Abnahme:
- Navigation funktioniert bis Prompt, Antwort und Validatorausgabe.
- Keine Kennzahl wird aus verschiedenen Experimenten zusammengesetzt.
- Listenendpunkte übertragen keine großen Artefakte.
- Bestehende Dashboardfunktionen bleiben verfügbar.

Nicht umsetzen:
- noch kein React-/Vite-Neubau
- keine MetriLLM- oder Harbor-Frontendkopie
```

### 19.17 Prompt 15 – Reale Kalibrierung der Quick-Suite

```text
Ziel:
Kalibriere Laufzeit, Taskauswahl und Flakiness mit realen lokalen Modellen,
ohne die produktive Standardausführung umzuschalten.

Voraussetzungen:
- Alle automatisierten Tests der vorherigen Prompts sind grün.
- Ein Betreiber hat Testnodes und Modelle ausdrücklich freigegeben.

Arbeitsauftrag:
1. Wähle mindestens drei repräsentative Modellklassen für 12–24 GB VRAM:
	schnell/klein, mittel und langsam/grenzwertig.
2. Erfasse vor jedem Lauf Modellhash, Node, effektive Parameter, Endpoint,
	Manifest und Systemzustand.
3. Führe Quick je Modell mindestens zweimal mit identischem Manifest aus.
4. Messe Dauer je Adapter, Gesamtdauer, Taskvarianz, Timeoutquote,
	fehlende/ungültige Antworten und Ressourcenprobleme.
5. Verändere Taskset oder Budgets nicht zwischen Wiederholungen.
6. Analysiere Flakiness taskweise. Änderungen erfordern eine neue
	Task-Set-Version mit dokumentierter Begründung.
7. Prüfe, ob die Suite starke und schwache Modelle unterscheidet und nicht nur
	Geschwindigkeit misst.
8. Schreibe auf Basis der Messdaten Quick V1 final fest.

Abnahme:
- typische Gesamtdauer liegt bei 20–30 Minuten
- kein Lauf überschreitet 40 Minuten unkontrolliert
- Timeout- und Teilresultatpfade funktionieren real
- Rangunterschiede sind taskweise erklärbar
- flaky Tasks sind markiert, korrigiert oder entfernt
- finaler Task- und Profilhash ist versioniert

Sicherheitsregeln:
- keine Last auf produktive Endpoints ohne Freigabe
- keine Modell-Downloads ohne Freigabe
- keine Secrets in Ergebnisartefakten

Nicht umsetzen:
- keine V0.2-Abschaltung
- keine verschiedenen Task-Set-Versionen zusammenranken
```

### 19.18 Prompt 16 – Full-Profil und V0.2-Kompatibilität

```text
Ziel:
Überführe vorhandene Tier-Benchmarks kontrolliert in Adapter und ein
Full-Profil, ohne Quick aufzublähen.

Arbeitsauftrag:
1. Erfasse die exakte Semantik der Tier-1-, Tier-2- und Tier-3-Skripte,
	einschließlich Sampling, KV-Matrix, Writer, Manifeste und Fehlerpfade.
2. Bilde aktive Benchmarks über bestehende oder neue Adapter ab. Verwende
	denselben Adaptervertrag wie Quick, aber eigene Full-Profile und Tasksets.
3. Behalte die KV-Matrix nur in Full oder Config-Sweep.
4. Vergleiche auf mindestens einem Modell V0.2 und V0.3 bei identischer
	effektiver Konfiguration und identischem Taskset.
5. Erkläre jede Ergebnisabweichung. Ungeklärte Abweichungen blockieren die
	Umschaltung.
6. Legacy-Shellskripte bleiben bis zur nachgewiesenen Parität verfügbar.

Tests:
- Adapterparser für alle aktiven V0.2-Benchmarks
- Full-Profil-Dry-Run
- Fehler- und Timeoutpfade
- KV-Matrix erzeugt getrennte Konfigurationsidentitäten
- Writer-Idempotenz
- Vergleichsfixtures V0.2 gegen V0.3

Abnahme:
- Aktive V0.2-Benchmarks sind im Full-Profil abbildbar.
- Quick bleibt unverändert unter seiner Laufzeitgrenze.
- Unterschiede sind erklärt und dokumentiert.

Nicht umsetzen:
- keine Deep-/Harbor-Integration
- V0.2 noch nicht entfernen
```

### 19.19 Prompt 17 – Veröffentlichung und sichere Distribution

```text
Ziel:
Bereite V0.3 für ein öffentliches GitHub-Repository vor, ohne private
Nexus-Infrastruktur offenzulegen.

Arbeitsauftrag:
1. Führe Secret- und Privacy-Scan über alle versionierbaren Dateien und die
	Historie des neuen Projekts aus.
2. Entferne oder ersetze produktive Hosts, Nutzer, Passwörter, Tokens,
	Modell-URLs, Datenbanken, Logs, Resultate und absolute lokale Pfade.
3. Stelle neutrale Beispielkonfigurationen, JSON-Schemas und synthetische
	Fixtures bereit.
4. Dokumentiere Betriebsarten:
	- einzelner OpenAI-kompatibler Endpoint
	- mehrere konfigurierbare Nodes
	- optionaler Nexus-Download-/Serving-Workflow
5. Dokumentiere Installation, Smoke, Quick-Dry-Run, Quick-Run,
	Dashboardstart, Adapterentwicklung und Diagnose.
6. Erstelle Third-Party-Notices mit Lizenz und Commit-Pinning.
7. Richte CI für Lint, Typprüfung, Unit-, Contract-, Migration-, Security- und
	Fake-Endpoint-Tests ein. CI benötigt keine produktiven Secrets.
8. Definiere Versionierung und Upgradepfad für Profile, Tasksets, Schema und
	Adapter.
9. Kennzeichne generische und Nexus-spezifische Funktionen klar.

Abnahme:
- Frischer Clone installiert und testet ohne Nexus-Infrastruktur.
- Smoke-/Dry-Run funktioniert mit Beispielkonfiguration.
- CI ist vollständig grün.
- Secret-Scan meldet keine produktiven Werte.
- Lizenzen und Quellen aller Komponenten sind dokumentiert.

Nicht umsetzen:
- keine produktive Konfiguration committen
- keine privaten Datenbanken oder Resultate veröffentlichen
```

### 19.20 Prompt 18 – Kontrollierte Produktivumschaltung

```text
Ziel:
Schalte erst nach nachgewiesener Parität und Rückfallmöglichkeit kontrolliert
von V0.2 auf V0.3 um.

Voraussetzungen:
- alle automatisierten Tests grün
- Quick-Kalibrierung abgenommen
- Full-Parität abgenommen
- Backup von DB, Konfiguration und Run-Skripten vorhanden
- Betreiberfreigabe liegt vor

Arbeitsauftrag:
1. Definiere Feature-Flag oder expliziten Einstieg zur Auswahl V0.2/V0.3.
2. Migriere keine produktive DB ohne Backup, Integritätsprüfung und getesteten
	Restore.
3. Führe zuerst V0.3-Smoke, dann Quick auf genau einer freigegebenen Node aus.
4. Prüfe Active-Flag, Logs, Status, Artefakte, Dashboard und Cleanup.
5. Erweitere danach schrittweise auf weitere Nodes.
6. Überwache erste Läufe auf verwaiste Prozesse, doppelte Writes,
	Budgetüberschreitung und inkonsistente Manifeste.
7. Dokumentiere Rollbackkriterien und führe einen Rollback-Test aus.
8. Setze V0.3 erst nach erfolgreicher Beobachtungsphase als Standard.
9. Archiviere V0.2, entferne es aber nicht im selben Schritt.

Abnahme:
- V0.3 funktioniert auf freigegebenen Nodes.
- Kein Run überschreitet Grenzen unkontrolliert.
- Rollback auf V0.2 ist getestet.
- Dashboard zeigt Quick und Task-Drill-down vollständig.
- Keine verwaisten Prozesse oder inkonsistenten Suitezustände.

Stop-Regel:
Bei Datenverlust, unbekannter Ergebnisabweichung, Secret-Leak, verwaistem
Prozess, fehlgeschlagenem Restore oder unerklärter Laufzeitüberschreitung
sofort auf V0.2 zurückschalten und Ursache untersuchen.
```

### 19.21 Optionaler Prompt 19 – Harbor als Deep-Adapter

Dieser Prompt wird erst nach stabiler V0.3-Produktivumschaltung ausgeführt.

```text
Ziel:
Integriere Harbor ausschließlich als optionales Deep-Profil für Finalisten.

Arbeitsauftrag:
1. Pinne eine Harbor-Version und dokumentiere Lizenz, Pythonversion,
	Containeranforderungen und lokale Modell-/Agentwege.
2. Erstelle einen Proof of Concept mit genau einem geeigneten Task und einem
	freigegebenen lokalen Endpoint.
3. Halte Harbor-Jobdaten getrennt; importiere Aggregate, Taskstatus, Dauer,
	Artefaktreferenzen und Versionen in das kanonische Nexus-Schema.
4. Prüfe den Harbor Viewer als separate Ansicht für Harbor-Jobs. Das
	Nexus-Dashboard bleibt die übergreifende Quelle.
5. Definiere einen kleinen versionierten Deep-Subset statt der Vollsuite.
6. Dokumentiere Container-, Speicher-, Netzwerk- und Sicherheitsgrenzen.

Abnahme:
- Harbor kann vollständig deaktiviert werden, ohne Quick/Full zu beeinflussen.
- Deep-Resultate sind als eigenes Level gekennzeichnet.
- Deep-Scores werden nicht mit Quick oder Full vermischt.
- Cleanup entfernt Taskcontainer und temporäre Ressourcen.

Nicht umsetzen:
- Harbor nicht zur Control Plane machen
- Quick-Runner und Nexus-Node-Orchestrierung nicht ersetzen
```

### 19.22 Empfohlene Arbeitsweise mit den Prompts

1. Pro Prompt einen eigenen Branch oder mindestens einen klar abgegrenzten
	Commit verwenden.
2. Nach jedem Prompt die Abnahmekriterien prüfen und das Ergebnis reviewen.
3. Bei fehlgeschlagener Abnahme den Prompt korrigieren, nicht mit dem nächsten
	Schritt fortfahren.
4. Prompt 15, 18 und 19 benötigen ausdrücklich Betreiberfreigabe, weil sie
	reale Nodes, produktive Daten oder längere Workloads betreffen können.
5. Neue Erkenntnisse werden zuerst in diesem Konzept dokumentiert. Änderungen
	an Profilen, Tasksets, Schema oder Scores erfordern eine neue Version.


