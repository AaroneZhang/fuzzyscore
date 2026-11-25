# PLAYBOOK — running fuzzyscore as an AI agent

fuzzyscore is built for the agent workflow: cold songs arrive as a pile of
**fuzzy clues** and the agent reconciles them into a practice pack.  This
file is the operating manual — for humans and for LLM agents.

## The fuzzy clues

| Clue | Where you find it | Reliability | Module |
|---|---|---|---|
| Chord sheet above lyrics | chord tabs sites, forums | harmony solid, rhythm absent | `chordchart.py` |
| ASCII tab on a webpage | tabs sites, blog posts | pitch order OK, spacing is *proportional*, not rhythmic; mute ghosts, no bar lines | `notation.parse_tab_block` |
| Rough MIDI | audio→MIDI services (Basic Pitch etc.) | pitch+time real, but polyphonic bleed, wrong octaves, no meter/sections | `midiio.parse_midi` + `quantize.py` |
| The recording itself | streaming / user files | ground truth, needs a transcription step before it becomes MIDI | out of scope (use demucs + Basic Pitch) |

No single clue is trustworthy.  Together they are: the chord sheet says
*which pitches are legal in each bar*, the MIDI says *when and how long*,
the ASCII tab says *which order and register*.  fuzzyscore's job is the
reconciliation and the bookkeeping (edit logs, audit, single-source
output).

## Standard flows

### A. Chord sheet only (coldest case)
```
fuzzyscore chords chart.txt --list          # review the harmonic map
# then ask your agent (or hand-write) a bass line per section and encode
# it with fuzzyscore.notation.Score / bar(...) — see demo.py rough_notes()
```

### B. Rough MIDI + chord sheet (the full reconciliation)
```
fuzzyscore midi-grid song.mid               # bpm estimate + per-bar pitch profile
fuzzyscore chords chart.txt --list          # confirm the two agree on structure
fuzzyscore build song.mid chart.txt out.musicxml --bpm 120 --title "Song"
fuzzyscore audit out.musicxml               # every bar must sum to the meter
fuzzyscore tab out.musicxml out.txt         # ASCII tab, same data source
fuzzyscore render out.musicxml out          # Staff+TabStaff PDF (needs lilypond)
```
The `build` step prints a **chord-prior edit log** — every note the chord
sheet "fixed" (bent or dropped).  An agent should READ the log before
shipping: a handful of edits = the prior did its job; hundreds = the MIDI
and the chart probably disagree structurally (wrong section order?) and a
human should arbitrate.

### C. ASCII tab only (web-scraped tab)
```
fuzzyscore tab2score tab.txt out.musicxml --title "Song" --key 2 --mode minor --tempo 120
```
Caveats an agent must respect:
- ASCII spacing is **proportional, not rhythmic** — durations are guesses
  refined by listening; note them as approximate in your README.
- Never guess the meter from spacing (the Roundabout lesson: a 15/8
  "reading" of a 4/4 riff).  Take the meter from the recording, the
  official metadata, or the chord sheet structure.
- Muted/ghost strokes in web tabs: encode as rests, never as pitches.

## Agent conventions baked into the data model

- Durations are **16th-note units** (MusicXML `divisions=4`).
- Score pitch strings are **sounding** pitch (`E1` = low E, MIDI 28);
  written notation is +1 octave, and `<transpose><octave-change>-1>`
  keeps MIDI playback honest.
- Bar item tuples accept a 3rd element of tie flags: `('B1', 12, 't')`
  ties into the next bar, `('B1', 4, 'T')` stops one.
- `Score.meter(beats, beat_type)` changes the meter mid-song (15/8 ↔ 4/4).
- Section names via `Score.section('Chorus')` become rehearsal marks in
  the PDF and `[Chorus]` labels in the ASCII tab.

## Quality gates before delivery

1. `fuzzyscore audit` — zero bad bars.
2. Edit log reviewed (flow B).
3. Register sanity: bass transcription between E1 and ~B3; anything above
   the cap is keyboard/vocal bleed and should become rests
   (`--low/--high` in `build`).
4. If LilyPond is available, render and *look* at page 1: rehearsal
   marks, meter changes, ties.

## Environment notes (macOS, sandboxed agents)

- Pure stdlib — no pip needed.
- LilyPond: drop the official ARM64 tarball into `./lilypond/` (or
  `./vendor/lilypond/`), or set `FUZZYSCORE_LILYPOND=/path/bin/lilypond`.
  Fontconfig's "No writable cache directories" warning is harmless.
- MIDI files are tiny and text-adjacent; keep them in the repo for tests.
