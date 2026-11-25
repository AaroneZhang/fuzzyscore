"""fuzzyscore.cli — agent-friendly subcommands.

    fuzzyscore tab2score IN.txt OUT.musicxml [--title T] [--key 2] [--mode minor]
                          [--tempo 120] [--drop-d] [--beats 4] [--beat-type 4]
        Parse a proportional ASCII tab (our own format) into MusicXML.

    fuzzyscore chords CHART.txt [--list]
        Parse a chord sheet; --list prints the flattened bar map (the
        harmonic prior an agent reviews before snapping).

    fuzzyscore midi-grid SONG.mid [--bpm 120] [--low 26] [--high 47]
        Rough MIDI -> 16th grid diagnostics: bpm estimate, slot table,
        per-bar pitch profile (what an agent reads to label sections).

    fuzzyscore build SONG.mid CHART.txt OUT.musicxml [--bpm ...] [--title ...]
        The full fuzzy pipeline: quantize MIDI, snap to the chord prior
        (edit log printed), emit MusicXML.

    fuzzyscore tab IN.musicxml OUT.txt [--title ...]
        ASCII 4-line tab with rhythm row, same data source as the PDF.

    fuzzyscore render IN.musicxml OUT_BASE
        LilyPond Staff+TabStaff PDF (needs the lilypond binary).

    fuzzyscore audit IN.musicxml
        Per-measure duration check against the time signature.

    fuzzyscore demo OUT_DIR
        Write the bundled synthetic example (chord sheet + deliberately
        imperfect MIDI) and run the full pipeline on it.
"""
import argparse
import os
import sys

from . import chordchart, lilypond, notation, quantize, texttab
from .midiio import parse_midi

FAIL = []


def cmd_tab2score(a):
    text = open(a.input, encoding='utf-8').read()
    S = notation.Score(a.title or os.path.splitext(os.path.basename(a.input))[0],
                       a.key, a.mode, beats=a.beats, beat_type=a.beat_type,
                       tempo=a.tempo, tempo_words=f'Tempo {a.tempo}',
                       prefer='flats' if a.mode == 'minor' and a.key <= -1 else 'sharps')
    base = {'E': 26, 'A': 33, 'D': 38, 'G': 43} if a.drop_d else None
    bars = notation.parse_tab_block(text, base=base)
    for b in bars:
        S.bar(b)
    S.save(a.output)
    print(f'{a.output}: {len(bars)} bars')


def cmd_chords(a):
    chart = chordchart.parse_chord_sheet(open(a.input, encoding='utf-8').read())
    bars = chart.flat_bars()
    if a.list:
        for i, (sec, sym, pc, pcs) in enumerate(bars):
            print(f'{i + 1:>4} {sec:<12} {sym}')
    print(f'{len(bars)} bars in {len(chart.sections)} sections')


def cmd_midi_grid(a):
    data = parse_midi(a.input)
    notes = data['notes']
    if not notes:
        print('no notes'); return 1
    bpm = a.bpm or quantize.estimate_bpm(notes) or 120.0
    print(f'notes={len(notes)} span={notes[-1][1] - notes[0][0]:.1f}s bpm~{bpm}')
    slots = quantize.fit_grid(notes, bpm)
    mono = quantize.collapse(slots)
    nbars = max(mono) // 16 + 1
    prof = quantize.bar_profile(mono, nbars)
    from .quantize import pc_of
    for i, w in enumerate(prof):
        items = ' '.join(f'{pc_of(p)}:{d}' for p, d in sorted(w.items(), key=lambda kv: -kv[1]))
        print(f'bar {i + 1:>4}: {items}')


def cmd_build(a):
    data = parse_midi(a.input)
    notes = data['notes']
    if not notes:
        print('no notes'); return 1
    bpm = a.bpm or quantize.estimate_bpm(notes) or 120.0
    slots = quantize.fit_grid(notes, bpm)
    mono = quantize.collapse(slots)
    chart = chordchart.parse_chord_sheet(open(a.chart, encoding='utf-8').read())
    bars = chart.flat_bars()
    snapped, log = quantize.snap_to_chords(mono, bars)
    nbars = max(mono) // 16 + 1
    print(f'-- chord-prior edit log ({len(log)} edits, bpm~{bpm}) --')
    for line in log:
        print(' ', line)
    sections = {}
    for i, (sec, *_rest) in enumerate(bars):
        if i + 1 <= nbars and (not sections or list(sections.values())[-1] != sec):
            sections[i + 1] = sec
    S = quantize.slots_to_score(snapped, a.title or 'Untitled',
                                key_fifths=a.key, mode=a.mode, tempo=int(round(bpm)),
                                prefer=a.prefer, subtitle=a.subtitle, sections=sections,
                                low=a.low, high=a.high)
    S.save(a.output)
    print(f'{a.output}: {nbars} bars, {len(log)} prior edits')


def cmd_tab(a):
    texttab.render_tab(a.input, a.output, a.title or '')


def cmd_render(a):
    ly = lilypond.score_to_ly(a.input)
    ly_path = a.output + '.ly'
    with open(ly_path, 'w', encoding='utf-8') as f:
        f.write(ly)
    ok, log = lilypond.compile_pdf(ly_path, a.output)
    print(('OK ' if ok else 'FAIL ') + a.output + '.pdf')
    if not ok:
        print(log)
        return 1


def cmd_audit(a):
    import re
    xml = open(a.input, encoding='utf-8').read()
    beats = int(re.search(r'<beats>(\d+)</beats>', xml).group(1))
    bt = int(re.search(r'<beat-type>(\d+)</beat-type>', xml).group(1))
    per = beats * 16 // bt
    bad = 0
    for i, m in enumerate(re.findall(r'<measure[^>]*>(.*?)</measure>', xml, re.S)):
        tot = sum(int(d) for d in re.findall(r'<note>(?:(?!</note>).)*?<duration>(\d+)</duration>', m, re.S))
        if tot != per:
            print(f'bar {i + 1}: {tot} != {per}')
            bad += 1
    print('ALL OK' if not bad else f'{bad} bad bars')


def cmd_demo(a):
    from . import demo as demo_mod
    demo_mod.run(a.out_dir)


def main(argv=None):
    p = argparse.ArgumentParser(prog='fuzzyscore', description=__doc__.splitlines()[1])
    sub = p.add_subparsers(dest='cmd', required=True)

    def sp(name, fn, **kw):
        q = sub.add_parser(name, **kw)
        q.set_defaults(fn=fn)
        return q

    q = sp('tab2score', cmd_tab2score)
    q.add_argument('input'); q.add_argument('output')
    q.add_argument('--title'); q.add_argument('--key', type=int, default=0)
    q.add_argument('--mode', default='major', choices=['major', 'minor'])
    q.add_argument('--tempo', type=int, default=120)
    q.add_argument('--beats', type=int, default=4); q.add_argument('--beat-type', type=int, default=4)
    q.add_argument('--drop-d', action='store_true')

    q = sp('chords', cmd_chords)
    q.add_argument('input'); q.add_argument('--list', action='store_true')

    q = sp('midi-grid', cmd_midi_grid)
    q.add_argument('input'); q.add_argument('--bpm', type=float)
    q.add_argument('--low', type=int, default=26); q.add_argument('--high', type=int, default=47)

    q = sp('build', cmd_build)
    q.add_argument('input'); q.add_argument('chart'); q.add_argument('output')
    q.add_argument('--bpm', type=float); q.add_argument('--title')
    q.add_argument('--key', type=int, default=2); q.add_argument('--mode', default='minor',
                                                                 choices=['major', 'minor'])
    q.add_argument('--prefer', default='sharps', choices=['sharps', 'flats'])
    q.add_argument('--subtitle'); q.add_argument('--low', type=int, default=26)
    q.add_argument('--high', type=int, default=47)

    q = sp('tab', cmd_tab)
    q.add_argument('input'); q.add_argument('output'); q.add_argument('--title')

    q = sp('render', cmd_render)
    q.add_argument('input'); q.add_argument('output')

    q = sp('audit', cmd_audit)
    q.add_argument('input')

    sp('demo', cmd_demo).add_argument('out_dir')

    args = p.parse_args(argv)
    sys.exit(args.fn(args) or 0)


if __name__ == '__main__':
    main()
