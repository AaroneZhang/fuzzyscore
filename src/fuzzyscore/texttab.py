"""fuzzyscore.texttab - ASCII 4-line bass tab rendered from the same
MusicXML that feeds the notation pipeline (single source of truth).
Includes the R rhythm row (w=whole h=half q=quarter e=eighth s=16th,
"." dotted, leading r = rest)."""
import re

STRING_BASE = [('G', 43), ('D', 38), ('A', 33), ('E', 28)]  # sounding midi
STEP_SEMI = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}

def pitch_to_sounding_midi(step, alter, octave):
    return (int(octave) + 1) * 12 + STEP_SEMI[step] + int(alter or 0)

def midi_to_tab(midi):
    best = None
    for name, base in STRING_BASE:
        fret = midi - base
        if 0 <= fret <= 20:
            if best is None or fret < best[1]:
                best = (name, fret)
    return best

def parse_musicxml(path):
    xml = open(path, encoding='utf-8').read()
    beats = int(re.search(r'<beats>(\d+)</beats>', xml).group(1))
    bt = int(re.search(r'<beat-type>(\d+)</beat-type>', xml).group(1))
    per_bar = beats * 16 // bt
    raw = re.findall(r'<measure[^>]*>(.*?)</measure>', xml, re.S)
    measures = []
    for m in raw:
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
                evs.append((start, dur, ('note', sounding)))
            else:
                evs.append((start, dur, ('rest',)))
        measures.append({'per': per_bar, 'events': evs})
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
    per = measures[0]['per']
    cell = 2 if per <= 16 else 3
    bar_w = per * cell
    bars_per_line = max(1, 100 // (bar_w + 2))
    word_map = dict(words)
    lines = [title_block] if title_block else []

    for start in range(0, len(measures), bars_per_line):
        chunk = measures[start:start + bars_per_line]
        label = ' '.join(f'[{word_map[i]}]' for i in range(start, start + len(chunk)) if i in word_map)
        rows = {s: [] for s, _ in STRING_BASE}
        rhy = []
        for m in chunk:
            grid = {s: ['--'] * per for s, _ in STRING_BASE}
            rg = ['--'] * per
            for st, dur, ev in m['events']:
                col = min(st, per - 1)
                letter = dur_letter(dur)
                if rg[col] == '--' or len(letter) > len(rg[col]):
                    rg[col] = letter[:cell]
                if ev[0] == 'rest':
                    continue
                tab = midi_to_tab(ev[1])
                if tab is None:
                    continue
                sname, fret = tab
                label_f = ('-' + str(fret)) if fret < 10 else str(fret)
                if grid[sname][col] == '--':
                    grid[sname][col] = label_f
            for s, _ in STRING_BASE:
                rows[s].append('|' + ''.join(grid[s]) + '|')
            rhy.append('|' + ''.join(rg) + '|')
        if label:
            lines.append(label)
        nums = '  '.join(str(start + bi + 1).ljust(bar_w + 1)
                         for bi in range(len(chunk)))
        lines.append('    ' + nums[:bar_w * len(chunk) + 3 * len(chunk)])
        lines.append(' R ' + ''.join(rhy))          # 节奏行:w全 h二分 q四分 e八分 s十六分 .=附点 r开头=休止
        for s, _ in STRING_BASE:
            lines.append(f' {s} ' + ''.join(rows[s]))
        lines.append('')

    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'{out}: {len(measures)} bars, {len(lines)} lines')

