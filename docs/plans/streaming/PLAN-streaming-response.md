# Implementierungsplan: schnelleres Streaming für Diktate

## Überblick

Ziel ist eine deutlich schnellere wahrgenommene Reaktion nach dem Loslassen der Maustaste. Der größte aktuelle Engpass ist nicht mehr das LLM-Streaming allein, sondern die sequenzielle Verarbeitung: Aufnahme stoppen, komplette Audiodatei schreiben, Whisper vollständig transkribieren, danach LLM verfeinern und erst am Ende einfügen. Der Plan führt Streaming deshalb stufenweise ein: zuerst messbare Latenz, dann Audio-Chunking und inkrementelle STT-Vorbereitung, anschließend tokenweises LLM-Streaming mit sichtbarem Fortschritt und optionalem früherem Paste-Zeitpunkt.

## Architekturentscheidungen

- Bestehenden stabilen Batch-Pfad beibehalten und Streaming als aktivierbare Pipeline-Variante einführen, damit Rückfall auf das aktuelle Verhalten jederzeit möglich bleibt.
- LLM-Streaming weiterverwenden, aber Callback-basiert in die Pipeline integrieren, damit sichtbarer Fortschritt schon während der Verfeinerung möglich ist.
- Audioaufnahme künftig zusätzlich in Chunks puffern, ohne die bestehende `stop()`-API sofort zu entfernen.
- Echte Whisper-Teiltranskription nur kontrolliert einführen, weil `faster-whisper` primär datei-/segmentbasiert arbeitet und zu kleine Chunks Qualität und Stabilität verschlechtern können.
- Erste schnelle Verbesserung: Whisper-Preload, keine unnötigen Tempfile-/Statusverzögerungen, frühere UI-Rückmeldung. Zweite Stufe: chunkbasierte Vorverarbeitung während der Aufnahme.

## Task List

### Phase 1: Messbarkeit und sichere Grundlage

#### Task 1: Latenz-Messpunkte ergänzen

**Beschreibung:** Die Pipeline erhält interne Zeitmessungen für Aufnahmeende, STT-Start, STT-Ende, LLM-Start, erstes LLM-Token, LLM-Ende und Paste-Ende. Dadurch wird sichtbar, welcher Abschnitt die Verzögerung verursacht.

**Acceptance criteria:**
- [ ] Log enthält pro Diktat die Dauer von STT, LLM bis erstem Token, gesamtem LLM und Paste.
- [ ] Messung funktioniert auch bei LLM-Fallback oder leerer Sprache.
- [ ] Keine UI-Popups mit Debugdaten.

**Verification:**
- [ ] `pytest tests/test_pipeline.py -q`
- [ ] Manuelles Diktat zeigt Timing-Zeilen im Log.

**Dependencies:** Keine

**Files likely touched:**
- `src/dictapaste/pipeline.py`
- `src/dictapaste/logging_setup.py`
- `tests/test_pipeline.py`

**Estimated scope:** S

#### Task 2: Streaming-Konfiguration ergänzen

**Beschreibung:** Eine neue Konfigurationsgruppe steuert Streaming-Verhalten, zunächst mit sicheren Defaults: Streaming aktiviert, STT-Chunking deaktiviert, Chunkdauer konfigurierbar.

**Acceptance criteria:**
- [ ] Config kann Streaming-Optionen laden, speichern und migrieren.
- [ ] Settings zeigen die Optionen als Dropdowns.
- [ ] Bestehende Configs bleiben kompatibel.

**Verification:**
- [ ] `pytest tests/test_config.py tests/test_config_versioning.py -q`

**Dependencies:** Task 1

**Files likely touched:**
- `src/dictapaste/config.py`
- `src/dictapaste/settings_dialog.py`
- `tests/test_config.py`
- `tests/test_config_versioning.py`

**Estimated scope:** M

### Checkpoint: Grundlage

- [ ] Alle Tests laufen.
- [ ] App startet mit alter Config.
- [ ] Log zeigt echte Latenzwerte.

### Phase 2: Sofort bessere Reaktion ohne riskante STT-Änderung

#### Task 3: LLM-Streaming sichtbar in Pipeline nutzen

**Beschreibung:** Der vorhandene `refine_stream()`-Callback wird in der Pipeline genutzt. Das Ergebnis wird weiterhin erst am Ende eingefügt, aber UI/Overlay zeigen bereits beim ersten sichtbaren Token, dass die Antwort läuft.

**Acceptance criteria:**
- [ ] Pipeline kann erste sichtbare LLM-Chunks empfangen.
- [ ] Thinking-Filter bleibt auch bei Streaming aktiv.
- [ ] Bei Abbruch wird kein Teiltext eingefügt.

**Verification:**
- [ ] `pytest tests/test_llm.py tests/test_pipeline.py -q`
- [ ] Manuell: Overlay reagiert beim ersten LLM-Token schneller.

**Dependencies:** Task 1

**Files likely touched:**
- `src/dictapaste/pipeline.py`
- `src/dictapaste/llm.py`
- `src/dictapaste/tray.py`
- `tests/test_pipeline.py`

**Estimated scope:** M

#### Task 4: Paste nach finalem Stream ohne zusätzliche Verzögerung

**Beschreibung:** Nach Abschluss des LLM-Streams wird unmittelbar eingefügt. Unnötige Zwischenbenachrichtigungen und doppelte Statuswechsel werden vermieden.

**Acceptance criteria:**
- [ ] Zwischen LLM-Ende und Paste gibt es keine künstliche Verzögerung.
- [ ] Status bleibt konsistent: `REFINING → PASTING → IDLE`.
- [ ] Fehlerpfad fällt weiterhin auf rohen Transkript zurück.

**Verification:**
- [ ] `pytest tests/test_pipeline.py -q`

**Dependencies:** Task 3

**Files likely touched:**
- `src/dictapaste/pipeline.py`
- `tests/test_pipeline.py`

**Estimated scope:** S

### Checkpoint: Schneller sichtbarer LLM-Start

- [ ] Nutzer sieht unmittelbar nach STT-Ende Streaming-Fortschritt.
- [ ] Thinking-Reste werden bei Stream und Non-Stream entfernt.
- [ ] Paste bleibt final und sauber.

### Phase 3: Audio-Chunking vorbereiten

#### Task 5: AudioRecorder um Chunk-Snapshot erweitern

**Beschreibung:** `AudioRecorder` speichert weiterhin Frames für den finalen Batch, kann aber zusätzlich sichere Snapshots der bisher aufgenommenen Audiodaten liefern. Dadurch kann Verarbeitung vorbereitet werden, ohne die Aufnahme zu stoppen.

**Acceptance criteria:**
- [ ] `snapshot()` liefert eine Kopie der bisherigen Audiodaten und Sample Rate.
- [ ] `stop()` funktioniert unverändert.
- [ ] Thread-Sicherheit bleibt gewährleistet.

**Verification:**
- [ ] Neue Unit-Tests für Snapshot-Verhalten.
- [ ] `pytest tests/test_pipeline.py tests/test_stt.py -q`

**Dependencies:** Task 2

**Files likely touched:**
- `src/dictapaste/audio.py`
- `tests/test_audio.py` oder bestehende Audiotests

**Estimated scope:** M

#### Task 6: STT-Warmup und Vorverarbeitung während Aufnahme

**Beschreibung:** Während der Aufnahme wird das Whisper-Modell sicher warm gehalten und optional eine leichte Vorverarbeitung auf Audio-Snapshots vorbereitet. Noch keine finale Teiltranskription, sondern risikoarme Vorbereitung für schnelleren STT-Start nach Release.

**Acceptance criteria:**
- [ ] Während Recording wird kein blockierender Whisper-Call auf dem UI-Thread ausgeführt.
- [ ] Nach Release kann STT sofort mit vorbereitetem Audio starten.
- [ ] Bei deaktiviertem Streaming bleibt Verhalten unverändert.

**Verification:**
- [ ] `pytest tests/test_pipeline.py tests/test_stt.py -q`
- [ ] Manuell: Release-to-STT-Start wird im Log kleiner.

**Dependencies:** Task 5

**Files likely touched:**
- `src/dictapaste/pipeline.py`
- `src/dictapaste/stt.py`
- `tests/test_pipeline.py`

**Estimated scope:** M

### Checkpoint: Schnellere STT-Startzeit

- [ ] Aufnahme kann weiter stabil gestoppt werden.
- [ ] Keine Audio-Datenverluste.
- [ ] Log zeigt kürzere Zeit zwischen Release und STT-Start.

### Phase 4: Inkrementelle STT als optionale Optimierung

#### Task 7: Experimentellen Chunk-Transcriber einführen

**Beschreibung:** Ein optionaler Transcriber verarbeitet längere Audiofenster, zum Beispiel alle 2 bis 4 Sekunden, und hält eine vorläufige Transkription bereit. Nach Release wird weiterhin ein finaler Whisper-Lauf oder eine finale Segment-Konsolidierung durchgeführt.

**Acceptance criteria:**
- [ ] Teiltranskription ist optional und per Setting deaktivierbar.
- [ ] Finale Ausgabe basiert auf konsolidiertem Text, nicht auf rohen instabilen Zwischenständen.
- [ ] Doppelte Segmente werden vermieden.

**Verification:**
- [ ] Unit-Tests für Segment-Zusammenführung.
- [ ] Manuelle Tests mit kurzen und langen Diktaten.

**Dependencies:** Task 6

**Files likely touched:**
- `src/dictapaste/stt.py`
- `src/dictapaste/pipeline.py`
- `tests/test_stt.py`
- `tests/test_pipeline.py`

**Estimated scope:** M

#### Task 8: LLM-Start mit finalisiertem oder vorläufigem Transkript prüfen

**Beschreibung:** Evaluieren, ob das LLM schon mit einem stabilen vorläufigen Transkript starten darf oder ob die Qualitätsverluste zu groß sind. Standard bleibt finaler STT-Text; optional kann ein aggressiver Schnellmodus getestet werden.

**Acceptance criteria:**
- [ ] Standardmodus nutzt finalen STT-Text.
- [ ] Experimenteller Schnellmodus ist klar als solcher benannt.
- [ ] Kein Teiltext wird eingefügt, wenn finale Konsolidierung abweicht.

**Verification:**
- [ ] Manuelle Vergleichstests: kurze deutsche Sätze, lange deutsche Sätze, englische Sätze, Übersetzungsmodus.

**Dependencies:** Task 7

**Files likely touched:**
- `src/dictapaste/pipeline.py`
- `src/dictapaste/settings_dialog.py`
- `tests/test_pipeline.py`

**Estimated scope:** M

### Checkpoint: Experimentelles End-to-End-Streaming

- [ ] Schnellmodus kann aktiviert/deaktiviert werden.
- [ ] Standardmodus bleibt stabil.
- [ ] Qualität und Latenz sind anhand Logs vergleichbar.

## Risiken und Gegenmaßnahmen

| Risiko | Impact | Gegenmaßnahme |
|---|---:|---|
| Whisper liefert bei kurzen Chunks schlechtere oder instabile Ergebnisse | Hoch | Chunk-STT nur optional, finaler Konsolidierungslauf bleibt Standard |
| Doppelte oder verschobene Segmente bei inkrementeller STT | Mittel | Segment-Zusammenführung separat testen |
| LLM beginnt mit vorläufig falschem Transkript | Hoch | LLM-Start standardmäßig erst nach finalem STT, Schnellmodus experimentell |
| Mehr Threads erzeugen Race Conditions | Mittel | Klare Queues/Events, Tests für Abbruch und Stop |
| Streaming-UI zeigt Thinking-Reste | Mittel | Bestehenden State-Machine-Think-Filter im Callback-Pfad erzwingen |

## Empfohlene Reihenfolge

Zuerst Tasks 1 bis 4 umsetzen, weil sie mit wenig Risiko die wahrgenommene Reaktion verbessern und Messbarkeit schaffen. Danach Tasks 5 und 6 für schnelleren STT-Start. Tasks 7 und 8 nur danach, weil echte inkrementelle Whisper-Verarbeitung der riskanteste Teil ist.

## Offene Fragen

- Soll der Nutzer während des LLM-Streamings bereits Text in einem Overlay sehen, oder reicht eine schnellere Fortschrittsanimation?
- Ist ein experimenteller Schnellmodus mit potenziell geringerer STT-Qualität akzeptabel?
- Soll Streaming standardmäßig aktiviert werden oder zunächst nur als Einstellung verfügbar sein?
