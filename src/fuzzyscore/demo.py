"""fuzzyscore.demo — synthetic cold-song example ("Night Walk").

Everything is generated from scratch (no copyrighted material):

* ``night-walk-chords.txt`` — a hand-typed chord sheet (the first fuzzy clue),
* ``night-walk-rough.mid`` — a *deliberately imperfect* MIDI transcription:
  the bass plays the chords but with a few wrong chromatic tones (passing
  mistakes an audio-to-MIDI service would make) and some keyboard bleed an
  octave above the register cap,
* the pipeline then quantizes the MIDI, snaps it to the chord prior (the
  edit log shows every correction), and emits MusicXML + ASCII tab.

Run via ``fuzzyscore demo OUT_DIR`` or ``python -m fuzzyscore.demo OUT_DIR``.
"""
import os

from .chordchart import parse_chord_sheet
from .cli import cmd_build, cmd_tab, cmd_audit
from .midiio import write_midi

CHORD_SHEET = """\
Night Walk (demo song)
[Verse]
| Bm | F#m | Bm | F#m |
[Pre-Chorus]
| Bm | D | E | A |
[Chorus]
| C#m | D | E | A |
| A | E | F#m | C#m |
"""


def rough_notes(bpm=120.0):
    """Bass line for the chart above + noise.  16 bars, 4/4, one bar/chord."""
    spb = 60.0 / bpm
    bars = ['B1', 'F#1', 'B1', 'F#1',                     # Verse
            'B1', 'D2', 'E2', 'A1',                       # Pre-Chorus
            'C#2', 'D2', 'E2', 'A1',                      # Chorus
            'A1', 'E2', 'F#1', 'C#2']                     # Chorus pt.2
    assert len(bars) == 16
    notes = []
    for b, root in enumerate(bars):
        t0 = b * 4 * spb
        rm = _midi(root)
        notes.append((t0, t0 + 1.75 * spb, rm, 96))            # root on 1
        notes.append((t0 + 1 * spb, t0 + 1.9 * spb, rm + 7, 80))   # 5th on 2
        notes.append((t0 + 2 * spb, t0 + 2.9 * spb, rm, 80))   # root on 3
        notes.append((t0 + 3 * spb, t0 + 3.4 * spb, rm + 12, 76))  # oct pickup
    # --- imperfections a real transcription would have ---
    notes.append((9 * 4 * spb + 1.0 * spb, 9 * 4 * spb + 1.4 * spb, _midi('C2'), 70))   # wrong chromatic
    notes.append((12 * 4 * spb + 2.5 * spb, 12 * 4 * spb + 3.7 * spb, _midi('G#1'), 70))  # foreign tone
    notes.append((4 * 4 * spb + 0.5 * spb, 4 * 4 * spb + 3.5 * spb, _midi('D4'), 60))   # keyboard bleed
    notes.append((13 * 4 * spb + 1.2 * spb, 13 * 4 * spb + 2.8 * spb, _midi('E4'), 60))  # bleed
    notes.sort()
    return notes


_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def _midi(name):
    step = name[0]
    rest = name[1:]
    acc = 0
    if rest and rest[0] in '#b':
        acc = 1 if rest[0] == '#' else -1
        rest = rest[1:]
    octv = int(rest)
    return (octv + 1) * 12 + _PC[step] + acc


def run(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    chart = os.path.join(out_dir, 'night-walk-chords.txt')
    with open(chart, 'w', encoding='utf-8') as f:
        f.write(CHORD_SHEET)
    mid = os.path.join(out_dir, 'night-walk-rough.mid')
    write_midi(mid, rough_notes(), bpm=120.0)

    print('== 1. chord prior ==')
    c = parse_chord_sheet(open(chart).read())
    bars = c.flat_bars()
    print(f'{len(bars)} bars: ' + ' '.join(sym for _, sym, _, _ in bars))

    print('\n== 2. quantize + snap to prior (edit log) ==')
    argv = ['build', mid, chart, os.path.join(out_dir, 'night-walk.musicxml'),
            '--bpm', '120', '--title', 'Night Walk (demo)',
            '--subtitle', 'fuzzyscore demo: chord sheet as harmonic prior']
    import sys
    old = sys.argv[1:]
    sys.argv[1:] = argv
    try:
        cmd_build(type('A', (), {
            'input': mid, 'chart': chart,
            'output': os.path.join(out_dir, 'night-walk.musicxml'),
            'bpm': 120.0, 'title': 'Night Walk (demo)', 'key': 2, 'mode': 'minor',
            'prefer': 'sharps',
            'subtitle': 'fuzzyscore demo: chord sheet as harmonic prior',
            'low': 26, 'high': 47})())
    finally:
        sys.argv[1:] = old

    print('\n== 3. ascii tab + audit ==')
    xml = os.path.join(out_dir, 'night-walk.musicxml')
    cmd_tab(type('A', (), {'input': xml,
                           'output': os.path.join(out_dir, 'night-walk.txt'),
                           'title': 'Night Walk (demo) — fuzzyscore'})())
    cmd_audit(type('A', (), {'input': xml})())

    print(f'''
done -> {out_dir}
  night-walk-chords.txt   the fuzzy clue (hand-typed chord sheet)
  night-walk-rough.mid    deliberately imperfect transcription
  night-walk.musicxml     reconciled score (see the edit log above)
  night-walk.txt          ASCII tab (same data source)

Next: fuzzyscore render {xml} {os.path.join(out_dir, 'night-walk')}
''')


if __name__ == '__main__':
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else 'demo-out')
