"""Tests for fuzzyscore — run with: python3 -m pytest tests/ (or unittest)."""
import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fuzzyscore import chordchart, notation, quantize  # noqa: E402
from fuzzyscore.midiio import parse_midi, write_midi  # noqa: E402
from fuzzyscore.texttab import render_tab  # noqa: E402
from fuzzyscore.lilypond import score_to_ly  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


class TestChordChart(unittest.TestCase):
    SHEET = """\
Some Song
[Verse]
Bm  F#m
        Bm        D
| E | A(2) |
(Chorus)
C#m - D - E - A
"""

    def test_parse_sections(self):
        c = chordchart.parse_chord_sheet(self.SHEET)
        self.assertEqual([n for n, _ in c.sections], ['Verse', 'Chorus'])

    def test_flat_bars(self):
        c = chordchart.parse_chord_sheet(self.SHEET)
        bars = c.flat_bars()
        syms = [s for _, s, _, _ in bars]
        self.assertEqual(syms, ['Bm', 'F#m', 'Bm', 'D', 'E', 'A', 'A',
                                'C#m', 'D', 'E', 'A'])

    def test_chord_tones(self):
        root, qual, pc, pcs = chordchart.parse_chord('Bbm7')
        self.assertEqual((root, pc), ('Bb', 10))
        self.assertEqual(pcs, {10, 1, 5, 8})
        self.assertIn(8, chordchart.parse_chord('E')[3])      # E major 3rd = G#
        self.assertIn(7, chordchart.parse_chord('Em')[3])     # Em minor 3rd = G

    def test_non_chords_ignored(self):
        self.assertIsNone(chordchart.parse_chord('Xylophone'))
        self.assertIsNone(chordchart.parse_chord('house'))


class TestNotation(unittest.TestCase):
    def test_tab_block_basic(self):
        tab = """
G|----------------|
D|----------------|
A|--------4---4---|
E|2---2-----------|
"""
        bars = notation.parse_tab_block(tab)
        self.assertEqual(len(bars), 1)
        midis = [ev[2] for ev in bars[0] if ev[0] == 'note']
        self.assertEqual(midis[0], 30)  # fret 2 on E string = sounding 30 (F#1)

    def test_two_digit_frets(self):
        tab = """
G|----------------|
D|----------------|
A|----------------|
E|10-12-----------|
"""
        bars = notation.parse_tab_block(tab)
        midis = [ev[2] for ev in bars[0] if ev[0] == 'note']
        self.assertEqual(midis, [38, 40])  # sounding: 28+10=D2, 28+12=E2

    def test_speed_digits_not_frets(self):
        # '1 2' adjacent = two separate 16ths, not fret 12
        tab = """
G|----------------|
D|----------------|
A|----------------|
E|1--2------------|
"""
        bars = notation.parse_tab_block(tab)
        midis = [ev[2] for ev in bars[0] if ev[0] == 'note']
        self.assertEqual(midis, [29, 30])  # sounding: frets 1, 2

    def test_duration_normalisation(self):
        tab = """
G|----------------|
D|----------------|
A|----------------|
E|2---------------|
"""
        S = notation.Score('N', 0, 'major', beats=4, beat_type=4, tempo=120)
        S.tab_block(tab)
        total = sum(it[2] for it in S.measures[0]['notes'])
        self.assertEqual(total, 16)  # padded to a full 4/4 bar

    def test_ties(self):
        S = notation.Score('T', 0, 'major', beats=4, beat_type=4, tempo=120)
        S.bar([('C2', 12, 't')])
        S.bar([('C2', 4, 'T')])
        xml = S.to_musicxml()
        self.assertIn('<tie type="start"/>', xml)
        self.assertIn('<tie type="stop"/>', xml)

    def test_meter_change(self):
        S = notation.Score('M', 2, 'major', beats=4, beat_type=4, tempo=120)
        S.bar([('C2', 4), ('D2', 4), ('E2', 4), ('G2', 4)])
        S.meter(7, 4)
        S.bar([('C2', 4)] * 7)
        xml = S.to_musicxml()
        self.assertIn('<beats>7</beats>', xml)
        self.assertEqual(len(S.measures), 2)
        self.assertEqual(S.measures[1]['meter'], (7, 4))
        self.assertEqual(sum(it[2] for it in S.measures[1]['notes']), 28)

    def test_audit_all_ok(self):
        S = notation.Score('A', 2, 'minor', beats=4, beat_type=4, tempo=100)
        for _ in range(4):
            S.bar([('B1', 4), ('F#1', 4), ('B1', 4), ('F#1', 4)])
        path = os.path.join(HERE, 'out_audit.musicxml')
        S.save(path)
        import re
        xml = open(path).read()
        per = 16
        bad = [i for i, m in enumerate(re.findall(r'<measure[^>]*>(.*?)</measure>', xml, re.S))
               if sum(int(d) for d in re.findall(r'<duration>(\d+)</duration>', m)) != per]
        self.assertEqual(bad, [])


class TestQuantize(unittest.TestCase):
    def _synth(self, bpm=120.0):
        spb = 60.0 / bpm
        notes = []
        for b, root in enumerate(['B1', 'F#1'] * 4):
            rm = (int(root[1] if False else 0))  # placeholder
        return notes

    def test_bpm_estimate(self):
        spb = 0.5
        notes = []
        for b in range(16):
            t0 = b * 4 * spb
            notes.append((t0, t0 + 1.5 * spb, 35, 90))
            notes.append((t0 + 2 * spb, t0 + 2.8 * spb, 35, 90))
        bpm = quantize.estimate_bpm(notes)
        self.assertTrue(bpm and 115 <= bpm <= 125, bpm)

    def test_grid_and_collapse(self):
        notes = [(0.0, 0.9, 35, 96), (0.5, 0.74, 36, 70), (2.0, 2.9, 35, 80)]
        slots = quantize.fit_grid(notes, 120.0)
        mono = quantize.collapse(slots)
        self.assertIn(0, mono)
        self.assertIn(4, mono)             # C2 is kept for the prior to review
        self.assertEqual(mono[4][0], 36)
        self.assertEqual(mono[16][0], 35)  # B1@2s survives

    def test_snap_to_chords(self):
        bars = [('V', 'D', 2, {2, 6, 9})]
        slots = {0: (35, 4, 90)}           # B1 over D chord
        out, log = quantize.snap_to_chords(slots, bars)
        self.assertEqual(out[0][0], 33)    # B1 → A1 (nearest chord tone within ±2)
        self.assertTrue(any('toward D' in l for l in log))

    def test_slots_to_score(self):
        slots = {16: (35, 8, 90), 24: (35, 4, 80)}
        S = quantize.slots_to_score(slots, 'T', drop_first_bar=True)
        self.assertEqual(len(S.measures), 2)  # bar1 dropped (keyboard lead-in)



class TestCli(unittest.TestCase):
    def test_tab2score_runs(self):
        tab = os.path.join(HERE, 'out_tt_tab_in.txt')
        out = os.path.join(HERE, 'out_tt_tab.musicxml')
        with open(tab, 'w') as f:
            f.write("G|----------------|\nD|----------------|\n"
                    "A|--------4---4---|\nE|2---2-----------|\n")
        env = dict(os.environ)
        env['PYTHONPATH'] = os.path.join(HERE, '..', 'src')
        r = subprocess.run([sys.executable, '-m', 'fuzzyscore.cli',
                            'tab2score', tab, out],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        xml = open(out).read()
        self.assertIn('<pitch>', xml)
        self.assertEqual(xml.count('<measure'), 1)


class TestTextTabDetails(unittest.TestCase):
    def test_rests_and_meter(self):
        S = notation.Score('TT2', 2, 'minor', beats=4, beat_type=4)
        S.bar([(None, 16)])                 # whole-bar rest
        S.meter(3, 4)
        S.bar([('B1', 4), ('B1', 4), ('B1', 4)])
        xml = os.path.join(HERE, 'out_tt2.musicxml')
        S.save(xml)
        out = os.path.join(HERE, 'out_tt2.txt')
        render_tab(xml, out)
        txt = open(out).read()
        self.assertIn('rw', txt)            # rest gets r + duration, not a bare w
        self.assertIn('-2', txt)            # B1 drawn as A-string fret 2
        # mixed meter forces one bar per line: two rhythm rows, not one shared line
        self.assertEqual(len(re.findall(r'^ R ', txt, re.M)), 2)


    def test_drop_d_tuning_reaches_tab(self):
        S = notation.Score('TT4', 2, 'minor', beats=4, beat_type=4)
        S.set_tuning([26, 33, 38, 43])
        S.bar([('D1', 16)])
        xml = os.path.join(HERE, 'out_tt4.musicxml')
        S.save(xml)
        out = os.path.join(HERE, 'out_tt4.txt')
        render_tab(xml, out)
        txt = open(out).read()
        self.assertIn(' D |-0', txt)       # low D drawn on the bottom (D) line

    def test_tie_is_not_reattacked(self):
        S = notation.Score('TT3', 2, 'minor', beats=4, beat_type=4)
        S.bar([('B1', 8, 't'), ('B1', 8, 'T')])
        xml = os.path.join(HERE, 'out_tt3.musicxml')
        S.save(xml)
        out = os.path.join(HERE, 'out_tt3.txt')
        render_tab(xml, out)
        txt = open(out).read()
        self.assertIn('~-', txt)            # sustain marker in the rhythm row
        self.assertEqual(txt.count('-2'), 1)  # one attack, not two

    def test_cross_bar_tie_is_not_reattacked(self):
        S = notation.Score('TT5', 2, 'minor', beats=4, beat_type=4)
        S.bar([('B1', 16, 't')])
        S.bar([('B1', 16, 'T')])
        xml = os.path.join(HERE, 'out_tt5.musicxml')
        S.save(xml)
        out = os.path.join(HERE, 'out_tt5.txt')
        render_tab(xml, out)
        txt = open(out).read()
        self.assertEqual(txt.count('-2'), 1)   # the second bar continues, no new attack
        self.assertIn('~-', txt)


class TestMidiIo(unittest.TestCase):
    def test_roundtrip(self):
        path = os.path.join(HERE, 'out_rt.mid')
        notes = [(0.0, 0.5, 35, 96), (0.5, 1.0, 40, 80)]
        write_midi(path, notes, bpm=120.0)
        d = parse_midi(path)
        self.assertEqual(len(d['notes']), 2)
        self.assertAlmostEqual(d['notes'][0][0], 0.0, places=2)
        self.assertAlmostEqual(d['notes'][1][1], 1.0, places=2)
        self.assertEqual([n[2] for n in d['notes']], [35, 40])


class TestTextTab(unittest.TestCase):
    def test_render(self):
        S = notation.Score('TT', 2, 'minor', beats=4, beat_type=4, tempo=120)
        S.section('Verse')
        S.bar([('B1', 4), ('F#1', 4), ('B1', 4), ('F#1', 4)])
        S.bar([('B1', 8), ('F#1', 8)])
        S.bar([('B1', 16)])
        xml = os.path.join(HERE, 'out_tt.musicxml')
        S.save(xml)
        out = os.path.join(HERE, 'out_tt.txt')
        render_tab(xml, out)
        txt = open(out).read()
        self.assertIn('[Verse]', txt)
        self.assertIn(' R ', txt)          # rhythm row present
        self.assertIn('w-', txt)           # whole-note letter
        self.assertIn('2', txt)            # fret numbers present


class TestLilypond(unittest.TestCase):
    def test_score_to_ly(self):
        S = notation.Score('LY', 2, 'minor', beats=4, beat_type=4, tempo=100,
                           tempo_words='Tempo 100', subtitle='sub')
        S.section('Verse')
        S.bar([('B1', 4), ('F#1', 4), ('B1', 4), ('F#1', 4)])
        xml = os.path.join(HERE, 'out_ly.musicxml')
        S.save(xml)
        ly = score_to_ly(xml)
        self.assertIn('\\new TabStaff', ly)
        self.assertIn('\\tempo 4 = 100', ly)
        self.assertIn('mark \\markup \\bold "Verse"', ly)
        self.assertIn('bass-tuning', ly)   # min sounding = 31 ≥ 28 → standard
        self.assertIn('Verse', ly)

    def test_drop_d_detection(self):
        S = notation.Score('DD', 2, 'minor', beats=4, beat_type=4, tempo=100)
        S.bar([('D1', 16)])                # sounding 26 < 28 → drop D
        xml = os.path.join(HERE, 'out_dd.musicxml')
        S.save(xml)
        self.assertIn('#bass-drop-d-tuning', score_to_ly(xml))


if __name__ == '__main__':
    unittest.main()
