# Changelog

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
