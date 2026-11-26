"""fuzzyscore.texttab - ASCII 4-line bass tab rendered from the same
MusicXML that feeds the notation pipeline (single source of truth).
Includes the R rhythm row (w=whole h=half q=quarter e=eighth s=16th,
"." dotted, leading r = rest)."""
import re

STRING_BASE = [('G', 43), ('D', 38), ('A', 33), ('E', 28)]  # sounding midi
STEP_SEMI = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}

def pitch_to_sounding_midi(step, alter, octave):
    return (int(octave) + 1) * 12 + STEP_SEMI[step] + int(alter or 0)

def _normalise_tuning(tuning):
    if not tuning:
        return list(STRING_BASE)
    if isinstance(tuning[0], int):
        return [(name, base) for (name, _), base in zip(STRING_BASE, tuning)]
    return list(tuning)

def midi_to_tab(midi, tuning=None):
    best = None
    for name, base in _normalise_tuning(tuning):
        fret = midi - base
        if 0 <= fret <= 20:
            if best is None or fret < best[1]:
                best = (name, fret)
    return best

def parse_musicxml(path):
    """Parse measures, keeping each measure's own meter and the staff tuning.

    The old renderer applied measure 1's meter to every bar, so any meter
    change produced misaligned bars.  Staff tuning is read from
    ``<staff-tuning>`` (written pitch; transpose -1 gives sounding), which is
    what lets a drop-D low D1 appear on the bottom line instead of vanishing.
    """
    xml = open(path, encoding='utf-8').read()
    raw = re.findall(r'<measure[^>]*>(.*?)</measure>', xml, re.S)

    tuning = None
    tm = re.findall(
        r'<staff-tuning line="(\d+)">\s*<tuning-step>([A-G])</tuning-step>'
        r'(?:\s*<tuning-alter>(-?\d+)</tuning-alter>)?\s*'
        r'<tuning-octave>(-?\d+)</tuning-octave>', xml)
    if tm:
        pairs = []
        for line, step, alter, octv in tm:
            midi = ((int(octv) + 1) * 12 + STEP_SEMI[step]
                    + int(alter or 0) - 12)
            pairs.append((int(line), midi))
        pairs.sort()
        tuning = [(name, midi) for name, (_, midi) in
                  zip(['G', 'D', 'A', 'E'], pairs)]

    measures = []
    beats, bt = 4, 4
    carry = None  # sounding pitch still held from the previous bar
    for m in raw:
        tm = re.search(r'<time[^>]*>.*?<beats>(\d+)</beats>.*?'
                       r'<beat-type>(\d+)</beat-type>', m, re.S)
        if tm:
            beats, bt = int(tm.group(1)), int(tm.group(2))
        per_bar = beats * 16 // bt
        evs, cursor = [], 0
        for n in re.findall(r'<note>.*?</note>', m, re.S):
            dur = int(re.search(r'<duration>(\d+)</duration>', n).group(1))
            is_chord = '<chord/>' in n
            start = evs[-1][0] if (is_chord and evs) else cursor
            if not is_chord:
                cursor += dur
            pm = re.search(r'<pitch><step>(\w)</step>(?:<alter>(-?\d)</alter>)?<octave>(\d)</octave>', n)
            if pm:
                sounding = pitch_to_sounding_midi(*pm.groups()) - 12
                # A tie stop continues the previous note; do not draw a new
                # attack (the old tab re-articulated every tied note).
                cont = (evs and evs[-1][2][0] == 'note'
                        and evs[-1][2][1] == sounding
                        and evs[-1][0] + evs[-1][1] == start)
                if (start == 0 and carry == sounding):
                    cont = True
                if ('<tie type="stop"/>' in n and not is_chord and cont):
                    # Keep the tie as its own span: the grid stays blank (no
                    # re-attack) and the rhythm row marks the sustain with ~.
                    evs.append((start, dur, ('tie',)))
                else:
                    evs.append((start, dur, ('note', sounding)))
            else:
                evs.append((start, dur, ('rest',)))
        carry = None
        for ev in reversed(evs):
            if ev[2][0] == 'note':
                carry = ev[2][1]
                break
        measures.append({'per': per_bar, 'events': evs, 'tuning': tuning})
    words = []
    for i, m in enumerate(raw):
        for w in re.findall(r'<words[^>]*font-weight="bold"[^>]*>([^<]+)</words>', m):
            words.append((i, w))
    return measures, words

DUR_LETTER = {16: 'w', 12: 'h.', 8: 'h', 6: 'q.', 4: 'q', 3: 'e.', 2: 'e', 1: 's'}

def dur_letter(d):
    return DUR_LETTER.get(d, f'x{d}')

def render_tab(path, out, title_block=''):
    measures, words = parse_musicxml(path)
    tuning = measures[0].get('tuning') if measures else None
    cell = 2 if max((m['per'] for m in measures), default=16) <= 16 else 3
    max_per = max((m['per'] for m in measures), default=16)
    bar_w = max_per * cell
    bars_per_line = max(1, 100 // (bar_w + 2))
    if len({m['per'] for m in measures}) > 1:
        # Mixed meters: one bar per line keeps every row aligned.
        bars_per_line = 1
    word_map = dict(words)
    lines = [title_block] if title_block else []

    for start in range(0, len(measures), bars_per_line):
        chunk = measures[start:start + bars_per_line]
        label = ' '.join(f'[{word_map[i]}]' for i in range(start, start + len(chunk)) if i in word_map)
        rows = {s: [] for s, _ in STRING_BASE}
        rhy = []
        nums = []
        for m in chunk:
            per = m['per']
            grid = {s: ['--'] * per for s, _ in STRING_BASE}
            rg = ['--'] * per
            # Notes first: a rest must never overwrite a simultaneous attack.
            for st, dur, ev in m['events']:
                if ev[0] != 'note':
                    continue
                col = min(st, per - 1)
                letter = dur_letter(dur)
                if rg[col] == '--' or len(letter) > len(rg[col]):
                    rg[col] = letter[:cell]
                tab = midi_to_tab(ev[1], tuning)
                if tab is None:
                    continue
                sname, fret = tab
                label_f = ('-' + str(fret)) if fret < 10 else str(fret)
                if grid[sname][col] == '--':
                    grid[sname][col] = label_f
            for st, dur, ev in m['events']:
                if ev[0] != 'tie':
                    continue
                col = min(st, per - 1)
                if rg[col] == '--':
                    rg[col] = '~-'
            for st, dur, ev in m['events']:
                if ev[0] != 'rest':
                    continue
                col = min(st, per - 1)
                if rg[col] == '--':
                    rg[col] = ('r' + dur_letter(dur))[:cell]
            for s, _ in STRING_BASE:
                rows[s].append('|' + ''.join(grid[s]) + '|')
            rhy.append('|' + ''.join(rg) + '|')
            nums.append(str(start + len(nums) + 1).ljust(per * cell + 1))
        if label:
            lines.append(label)
        lines.append('    ' + '  '.join(nums))
        lines.append(' R ' + ''.join(rhy))          # 节奏行:w全 h二分 q四分 e八分 s十六分 .=附点 r=休止
        for s, _ in STRING_BASE:
            label = 'D' if (s == 'E' and tuning and tuning[-1][1] < 28) else s
            lines.append(f' {label} ' + ''.join(rows[s]))
        lines.append('')

    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'{out}: {len(measures)} bars, {len(lines)} lines')
