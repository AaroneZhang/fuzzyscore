"""fuzzyscore.lilypond - MusicXML -> LilyPond .ly (Staff + TabStaff) and PDF.

Staff shows written pitch (= sounding + 12); TabStaff uses \transpose c c,
so frets are computed from the sounding pitch.  Drop-D is auto-detected
(min sounding midi < 28).  The lilypond binary is looked up via the
FUZZYSCORE_LILYPOND env var or PATH.
"""
# lily_export.py — MusicXML (my schema) -> LilyPond .ly with Staff + TabStaff
# Staff shows written pitch (= sounding + 12, same as existing PDFs);
# TabStaff gets \transpose c c, so frets are computed from sounding pitch.
import xml.etree.ElementTree as ET

DUR_LILY = {16: '1', 12: '2.', 8: '2', 6: '4.', 4: '4', 3: '8.', 2: '8', 1: '16'}
MAJOR_TONIC = {-6: 'gf', -5: 'df', -4: 'af', -3: 'ef', -2: 'bf', -1: 'f', 0: 'c',
               1: 'g', 2: 'd', 3: 'a', 4: 'e', 5: 'b', 6: 'fs'}
MINOR_TONIC = {-6: 'ef', -5: 'bf', -4: 'c', -3: 'g', -2: 'd', -1: 'a', 0: 'a',
               1: 'e', 2: 'b', 3: 'fs', 4: 'cs', 5: 'gs', 6: 'ds'}
STEP_LILY = {'C': 'c', 'D': 'd', 'E': 'e', 'F': 'f', 'G': 'g', 'A': 'a', 'B': 'b'}


def parse_musicxml(path):
    root = ET.parse(path).getroot()
    title = root.findtext('./work/work-title') or 'Untitled'
    part = root.find('part')
    measures = []
    meta = {}
    prev_meter = None
    for m in part.findall('measure'):
        mrec = {'marks': [], 'time': None, 'notes': []}
        # attributes: time signature changes (first measure also carries key)
        for attr in m.findall('attributes'):
            t = attr.find('time')
            if t is not None:
                beats, bt = t.findtext('beats'), t.findtext('beat-type')
                mrec['time'] = (beats, bt)
                if prev_meter is None:
                    k = attr.find('key')
                    if k is not None:
                        meta['fifths'] = int(k.findtext('fifths'))
                        meta['mode'] = k.findtext('mode') or 'major'
            tr = attr.find('transpose')
            if tr is not None:
                meta['octave_change'] = int(tr.findtext('octave-change') or 0)
        # directions: bold font-size 12 words = rehearsal marks; 15 = title; 10 = tempo/subtitle
        for d in m.findall('direction'):
            w = d.find('direction-type/words')
            if w is None:
                continue
            size = w.get('font-size', '')
            txt = (w.text or '').strip()
            if size == '15':
                meta['title'] = txt
            elif size == '10':
                meta.setdefault('lines10', []).append(txt)
            else:
                mrec['marks'].append(txt)
        for n in m.findall('note'):
            ties = {t.get('type') for t in n.findall('tie')}
            if n.find('rest') is not None:
                mrec['notes'].append(('rest', None, int(n.findtext('duration')), ties))
            else:
                p = n.find('pitch')
                step = p.findtext('step')
                alter = int(p.findtext('alter') or 0)
                octv = int(p.findtext('octave'))
                mrec['notes'].append(('note', (step, alter, octv), int(n.findtext('duration')), ties))
        measures.append(mrec)
        if mrec['time']:
            prev_meter = mrec['time']
    meta['title'] = title
    return meta, measures


def min_sounding_midi(measures):
    lo = None
    for m in measures:
        for kind, val, _, _ in m['notes']:
            if kind == 'note':
                step, alter, octv = val
                midi = (octv + 1) * 12 + {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}[step] + alter
                lo = midi if lo is None else min(lo, midi)
    return lo


def note_token(step, alter, octv):
    s = STEP_LILY[step]
    if alter == -1:
        s += 'f'
    elif alter == 1:
        s += 's'
    elif alter == -2:
        s += 'ff'
    elif alter == 2:
        s += 'ss'
    k = octv - 3  # lily: c' = middle C (C4) -> scientific oct 4
    if k > 0:
        s += "'" * k
    elif k < 0:
        s += ',' * (-k)
    return s


def ly_escape(s):
    return s.replace('\\', '\\\\').replace('"', '\\"')


def emit_measure(m, with_marks):
    out = []
    if with_marks:
        if m['time']:
            out.append(f"  \\time {m['time'][0]}/{m['time'][1]}")
        for w in m['marks']:
            out.append(f'  \\mark \\markup \\bold "{ly_escape(w)}"')
    elif m['time']:
        out.append(f"  \\time {m['time'][0]}/{m['time'][1]}")
    toks = []
    for kind, val, dur, ties in m['notes']:
        d = DUR_LILY.get(dur)
        if d is None:
            raise ValueError(f'unmapped duration {dur}')
        if kind == 'rest':
            toks.append('r' + d)
        else:
            step, alter, octv = val
            tok = note_token(step, alter, octv) + d
            if 'start' in ties:
                tok += '~'
            toks.append(tok)
    out.append('  ' + ' '.join(toks))
    return out


def tempo_from(meta):
    # among font-size-10 lines: the "Tempo N, ..." one carries the tempo,
    # the other is the subtitle
    tempo, subtitle = None, ''
    for line in meta.get('lines10', []):
        if line.startswith('Tempo') and tempo is None:
            rest = line[len('Tempo'):].lstrip()
            num = rest.split(',')[0].strip()
            tempo = num
            subtitle = rest[len(num):].lstrip(', ').strip()
        else:
            subtitle = line
    return tempo, subtitle


def score_to_ly(path, key_idx=None):
    meta, measures = parse_musicxml(path)
    # XML stores written pitch (sounding + 12); recover sounding for the
    # drop-D check via the transposition we emitted ourselves.
    lo_written = min_sounding_midi(measures)
    lo = None if lo_written is None else lo_written + 12 * meta.get('octave_change', 0)
    drop_d = lo is not None and lo < 28
    tonic = (MINOR_TONIC if meta.get('mode') == 'minor' else MAJOR_TONIC)[meta['fifths']]
    mode = meta.get('mode') or 'major'
    tempo, subtitle = tempo_from(meta)
    title = meta.get('title') or meta.get('title')
    keyref = f"Song {key_idx}" if key_idx else title

    L = []
    L.append('\\version "2.26.0"')
    L.append('\\language "english"')
    L.append('\\header {')
    L.append(f'  title = "{ly_escape(title)}"')
    if subtitle:
        L.append(f'  subtitle = "{ly_escape(subtitle)}"')
    L.append('  composer = "Bass"')
    L.append('}')
    L.append('')
    L.append('staffMusic = {')
    L.append(f'  \\key {tonic} \\{mode}')
    if tempo:
        L.append(f'  \\tempo 4 = {tempo}')
    for m in measures:
        L.extend(emit_measure(m, with_marks=True))
    L.append('}')
    L.append('')
    L.append('tabMusic = {')
    L.append(f'  \\key {tonic} \\{mode}')
    for m in measures:
        L.extend(emit_measure(m, with_marks=False))
    L.append('}')
    L.append('')
    tuning = "#'(26 33 38 43)" if drop_d else '#bass-tuning'
    L.append('\\score {')
    L.append('  \\new StaffGroup <<')
    L.append('    \\new Staff { \\clef bass \\staffMusic }')
    L.append(f'    \\new TabStaff \\with {{ stringTunings = {tuning} }} {{ \\transpose c c, \\tabMusic }}')
    L.append('  >>')
    L.append('  \\layout { indent = #0 }')
    L.append('}')
    L.append('\\paper { #(set-paper-size "a4") left-margin = 12 right-margin = 12 oddFooterMarkup = ##f evenFooterMarkup = ##f }')
    return '\n'.join(L) + '\n'




# ---------------- compile ----------------

import os
import shutil
import subprocess


def find_lilypond():
    exe = os.environ.get('FUZZYSCORE_LILYPOND')
    if exe and os.path.exists(exe):
        return exe
    found = shutil.which('lilypond')
    if found:
        return found
    # vendored copy? search upward from CWD (agent-friendly conventions:
    # ./lilypond or ./vendor/lilypond holding the official tarball layout)
    d = os.getcwd()
    for _ in range(4):
        for sub in ('', 'vendor'):
            guess = os.path.join(d, sub, 'lilypond', 'bin', 'lilypond')
            if os.path.exists(guess):
                return guess
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def compile_pdf(ly_path, out_base, lilypond_bin=None, timeout=180):
    """Run lilypond on ly_path, writing out_base.pdf. Returns (ok, log)."""
    exe = lilypond_bin or find_lilypond()
    if not exe or not os.path.exists(exe):
        return False, 'lilypond binary not found (set FUZZYSCORE_LILYPOND or install lilypond)'
    out_dir = os.path.dirname(os.path.abspath(out_base)) or '.'
    os.makedirs(out_dir, exist_ok=True)
    try:
        r = subprocess.run([exe, '-dno-point-and-click', '-o', os.path.abspath(out_base),
                            os.path.abspath(ly_path)],
                           capture_output=True, text=True, timeout=timeout, cwd=out_dir)
    except subprocess.TimeoutExpired:
        return False, 'lilypond timed out'
    ok = r.returncode == 0 and os.path.exists(out_base + '.pdf')
    return ok, (r.stderr or r.stdout)[-2000:]
