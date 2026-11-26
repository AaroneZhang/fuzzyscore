# Changelog

## 0.1.1 — 2026-11-26

Accuracy fixes for the generated score, found while auditing the demo:

- `quantize.slots_to_score` no longer drops bar 1 by default; the old default
  deleted real music. `--drop-first-bar` is now opt-in.
- `quantize.collapse` filters the register *before* clipping, so keyboard
  bleed can no longer shorten a real bass note; the old contained-note rule
  that silently deleted wrong low notes is gone (the chord prior now sees and
  logs them).
- `snap_to_chords` merges a bend into the note already ringing instead of
  creating a repeated attack / stutter.
- `cli tab2score` works again (it fed tab events to `Score.bar`); high-register
  octave doublings up to MIDI 60 are kept by default.
- `texttab`: per-measure meters, rests marked `r`, ties marked `~` without
  re-attacking, `<staff-tuning>` respected, drop-D low string labelled `D`.
- `lilypond`: drop-D uses `#bass-drop-d-tuning` (raw MIDI numbers are invalid
  in `stringTunings`); add regression tests for the CLI, rests, meter changes
  and ties (23 tests).
- Refresh the bundled `examples/night-walk.*` outputs.

## 0.1.0 — 2026-11-25

Initial release.

- `notation`: proportional ASCII tab → MusicXML (two-digit frets, mid-song
  meter changes, ties across bars, duration normalisation, beaming).
- `chordchart`: human chord sheets → per-bar harmonic prior
  (`| Bm | F#m D |`, `Bm(2)`, chords-above-lyrics, `[Section]` headers).
- `midiio`: stdlib MIDI reader/writer, tempo-map aware.
- `quantize`: BPM autocorrelation, windowed grid fit, polyphonic bleed
  removal, chord-prior snap with full edit log.
- `lilypond`: Staff+TabStaff renderer with rehearsal marks, drop-D
  autodetection, vendored-tarball discovery.
- `cli`: tab2score / chords / midi-grid / build / tab / render / audit / demo.
- Synthetic demo "Night Walk" + 19 unit tests.
