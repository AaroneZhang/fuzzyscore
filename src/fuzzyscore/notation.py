"""fuzzyscore.notation - bass tab / note events -> MusicXML.

Durations are in 16th-note units (MusicXML divisions=4 per quarter).
Written pitch = sounding pitch + 1 octave (standard bass-notation
practice; an octave-change of -1 in the XML keeps MIDI playback honest).
Ported from the session-proven lib_notation.py, including proportional
ASCII-tab parsing, two-digit fret disambiguation (10..24), meter changes,
ties via 3-tuples, per-measure duration normalisation and beaming.
"""
# lib_notation.py — bass tab → MusicXML (for verovio engraving)
# Conventions: durations in 16th-note units (MusicXML divisions=4 per quarter,
# so 1 division = one 16th). Written pitch = sounding pitch + 1 octave
# (standard bass-notation practice; README explains).
import re

STRING_BASE = {'E': 28, 'A': 33, 'D': 38, 'G': 43}  # sounding MIDI of open strings (E1=28)
DIV = 4  # MusicXML divisions per quarter

PC_SHARPS = {0:('C',0),1:('C',1),2:('D',0),3:('D',1),4:('E',0),5:('F',0),
             6:('F',1),7:('G',0),8:('G',1),9:('A',0),10:('A',1),11:('B',0)}
PC_FLATS  = {0:('C',0),1:('D',-1),2:('D',0),3:('E',-1),4:('E',0),5:('F',0),
             6:('G',-1),7:('G',0),8:('A',-1),9:('A',0),10:('B',-1),11:('B',0)}

DUR_TYPE = {1:('16th',0), 2:('eighth',0), 3:('eighth',1), 4:('quarter',0),
            6:('quarter',1), 8:('half',0), 12:('half',1), 16:('whole',0)}
SPLIT_ORDER = [16, 12, 8, 6, 4, 3, 2, 1]
QUAL = (1, 2, 3)  # durations eligible for beaming (16th, 8th, dotted 8th)

def split_dur(d):
    out = []
    while d > 0:
        for u in SPLIT_ORDER:
            if u <= d:
                out.append(u); d -= u; break
    return out

def midi_to_sao(midi, prefer='sharps'):
    pc, octv = midi % 12, midi // 12 - 1
    table = PC_FLATS if prefer == 'flats' else PC_SHARPS
    step, alter = table[pc]
    return step, alter, octv

def pitch_str_to_sao(p):
    m = re.match(r'^([A-G])([#b]*)(-?\d+)$', p)
    if not m: raise ValueError(f'bad pitch {p!r}')
    step, acc, octv = m.group(1), m.group(2), int(m.group(3))
    alter = acc.count('#') - acc.count('b')
    return step, alter, octv + 1  # written = stated + 8ve

def sao_from_midi_written(midi_sounding, prefer):
    return midi_to_sao(midi_sounding + 12, prefer)

# ---------------- tab parsing ----------------

def parse_tab_block(text, base=None):
    """Parse 4-line (G/D/A/E) tab blocks -> list of bars.
    bar = list of ('note', pos, midi_sounding) / ('rest', pos, dur).
    base: optional {row: midi} override for alternate tunings (e.g. drop-D)."""
    if base is None:
        base = STRING_BASE
    lines = [l.rstrip('\n') for l in text.splitlines()]
    groups, cur = [], {}
    order = ['G', 'D', 'A', 'E']

    def flush():
        nonlocal cur
        if all(k in cur for k in order):
            groups.append([cur[k] for k in order])
        cur = {}

    for l in lines:
        m = re.match(r'^\s*([GDAE])\s*\|{1,2}(.*)$', l)
        if m:
            cur[m.group(1)] = m.group(2)
            if m.group(1) == 'E':
                flush()
        elif l.strip() and not l.strip().startswith(('[', '(', '=', '-', 'T', 'N')):
            flush()
    flush()

    bars = []
    for g in groups:
        rows = [l.replace('o', '').replace('O', '') for l in g]
        cells = [r.split('|') for r in rows]
        n = min(len(c) for c in cells)
        for i in range(n):
            col = [c[i] for c in cells]
            if any(re.search(r'\d', c) for c in col):
                bars.append(parse_cell(col, base))
    return bars

def parse_cell(rows, base=None):
    """rows: [G, D, A, E] strings of one measure -> events list.
    ('note', pos, midi_sounding); leading silence becomes ('rest', 0, dur)."""
    if base is None:
        base = STRING_BASE
    tones = {}
    for s, row in zip('GDAE', rows):
        i = 0
        while i < len(row):
            ch = row[i]
            if ch.isdigit():
                pos = i
                fret = int(ch); i += 1
                # two-digit fret only if the pair stays in a valid range (10..24);
                # otherwise adjacent digits are consecutive fast notes (e.g. '67', '424')
                if i < len(row) and row[i].isdigit():
                    pair = fret * 10 + int(row[i])
                    if 10 <= pair <= 24:
                        fret = pair; i += 1
                midi = base[s] + fret
                if pos not in tones or midi < tones[pos]:
                    tones[pos] = midi
            else:
                i += 1
    events = []
    positions = sorted(tones)
    for j, pos in enumerate(positions):
        if j == 0 and pos > 0:
            events.append(('rest', 0, pos))
        events.append(('note', pos, tones[pos]))
    return events

# ---------------- score builder ----------------

class Score:
    def __init__(self, title, key_fifths, mode='major', beats=4, beat_type=4,
                 tempo=None, tempo_words=None, prefer='sharps',
                 subtitle=None, composer=None):
        self.title, self.subtitle, self.composer = title, subtitle, composer
        self.key_fifths, self.mode = key_fifths, mode
        self.beats, self.beat_type = beats, beat_type
        self.tempo, self.tempo_words = tempo, tempo_words
        self.prefer = prefer
        self.measures = []  # {'notes': [...], 'word': str|None, 'meter': (b,bt)|None}
        self._pending_word = None
        self._pending_play = 1
        self._current_meter = (beats, beat_type)

    def section(self, name, play=1):
        self._pending_word = name
        self._pending_play = play
        return self

    def meter(self, beats, beat_type):
        """中途换拍号(如 15/8 ↔ 4/4);对后续所有小节生效直到再次调用"""
        self._current_meter = (beats, beat_type)
        return self

    def _append_measure(self, items, word=None):
        # 归一化:小节总时值必须等于拍号要求(4/4→16, 7/4→28, 15/8→30)
        b, bt = self._current_meter
        expect = b * 16 // bt
        total = sum(it[2] for it in items)
        if total != expect:
            items = list(items)
            while total > expect and items:    # 超长:从尾部缩短音符
                it = items[-1]
                cut = min(it[2], total - expect)
                if cut >= it[2]:
                    items.pop(); total -= it[2]
                else:
                    items[-1] = (it[0], it[1], it[2] - cut) + tuple(it[3:])
                    total -= cut
            if total < expect:                 # 不足:补休止符
                items.append(('rest', None, expect - total, ''))
        self.measures.append({'notes': items, 'word': word, 'meter': self._current_meter})

    def _finalize_bar(self, events, word=None, bar_len=16):
        tones = [(pos, val) for k, pos, val in events if k == 'note']
        items, cursor = [], 0
        for idx, (pos, val) in enumerate(tones):
            if pos > cursor:
                items.append(('rest', None, pos - cursor)); cursor = pos
            gap = (tones[idx + 1][0] - pos) if idx + 1 < len(tones) else (bar_len - pos)
            dur = max(1, min(gap, 16))
            items.append(('note', val, dur))
            cursor = pos + dur
        if cursor < bar_len:
            items.append(('rest', None, bar_len - cursor))
        self._append_measure(items, word)

    def tab_block(self, text, bar_len=16, base=None):
        bars = parse_tab_block(text, base)
        for play in range(self._pending_play):
            for bi, bar_events in enumerate(bars):
                word = self._pending_word if (play == 0 and bi == 0) else None
                self._finalize_bar(bar_events, word, bar_len)
        self._pending_word, self._pending_play = None, 1
        return self

    def bar_from_tab(self, text, word=None, bar_len=16, base=None):
        bars = parse_tab_block(text, base)
        if len(bars) != 1:
            raise ValueError(f'expected 1 bar, got {len(bars)}')
        self._finalize_bar(bars[0], word, bar_len)
        return self

    def bar(self, notes, word=None):
        """Manual bar: notes = [(pitch_str_or_None, dur16), ...] 或 (p, d, flags)。
        flags: 't'=tie start, 'T'=tie stop(可组合 'tT')。跨小节延音:前小节末 (p,d,'t'),后小节首 (p,d,'T')。"""
        items = []
        for n in notes:
            p, d = n[0], n[1]
            fl = n[2] if len(n) > 2 else ''
            if p is None:
                items.append(('rest', None, d, ''))
            else:
                items.append(('pitch', p, d, fl))
        w = word if word is not None else self._pending_word
        for i in range(self._pending_play):
            self._append_measure(items, w if i == 0 else None)
        self._pending_word, self._pending_play = None, 1
        return self

    # ---------------- MusicXML ----------------
    @staticmethod
    def _esc(s):
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def _measure_pieces(self, m):
        """Flatten note list into pieces with start offsets. 同一音符拆多段时自动加延音线;
        条目可带第 4 元素 flags('t'=tie start,'T'=tie stop,用于跨小节延音)。"""
        pieces, cursor = [], 0
        for it in m['notes']:
            kind, val, dur = it[0], it[1], it[2]
            fl = it[3] if len(it) > 3 else ''
            parts = split_dur(dur)
            for i, u in enumerate(parts):
                tie_stop = (i > 0) or ('T' in fl)
                tie_start = (i < len(parts) - 1) or ('t' in fl)
                pieces.append({'kind': kind, 'val': val, 'dur': u, 'start': cursor,
                               'tie_start': tie_start and kind != 'rest',
                               'tie_stop': tie_stop and kind != 'rest'})
                cursor += u
        return pieces

    @staticmethod
    def _add_beams(pieces):
        def beat_of(p): return p['start'] // 4
        def inside_beat(p): return beat_of(p) == ((p['start'] + p['dur'] - 1) // 4)
        i, n = 0, len(pieces)
        while i < n:
            p = pieces[i]
            if p['kind'] != 'rest' and p['dur'] in QUAL and inside_beat(p):
                j, group = i, []
                while j < n:
                    q = pieces[j]
                    if q['kind'] != 'rest' and q['dur'] in QUAL and inside_beat(q) and beat_of(q) == beat_of(p):
                        group.append(j); j += 1
                    else:
                        break
                if len(group) >= 2:
                    for idx, gpos in enumerate(group):
                        pieces[gpos]['beam1'] = 'begin' if idx == 0 else ('end' if idx == len(group) - 1 else 'continue')
                    r = 0
                    while r < len(group):
                        if pieces[group[r]]['dur'] == 1:
                            r2 = r
                            while r2 < len(group) and pieces[group[r2]]['dur'] == 1:
                                r2 += 1
                            run = group[r:r2]
                            if len(run) >= 2:
                                for idx, gpos in enumerate(run):
                                    pieces[gpos]['beam2'] = 'begin' if idx == 0 else ('end' if idx == len(run) - 1 else 'continue')
                            else:
                                gpos = run[0]
                                pos_in_group = group.index(gpos)
                                pieces[gpos]['beam2'] = 'forward hook' if pos_in_group < len(group) - 1 else 'backward hook'
                            r = r2
                        else:
                            r += 1
                i = j
            else:
                i += 1
        return pieces

    def _piece_xml(self, p, indent='        '):
        t, dot = DUR_TYPE[p['dur']]
        extra = ('<dot/>' if dot else '')
        beams = ''
        if p.get('beam1'):
            beams += f'<beam number="1">{p["beam1"]}</beam>'
        if p.get('beam2'):
            beams += f'<beam number="2">{p["beam2"]}</beam>'
        if p['kind'] == 'rest':
            return [f'{indent}<note><rest/><duration>{p["dur"]}</duration>'
                    f'<voice>1</voice><type>{t}</type>{extra}</note>']
        if isinstance(p['val'], int):
            step, alter, octv = sao_from_midi_written(p['val'], self.prefer)
        else:
            step, alter, octv = pitch_str_to_sao(p['val'])
        alt = f'<alter>{alter}</alter>' if alter else ''
        ties = ''
        if p.get('tie_stop'):
            ties += '<tie type="stop"/>'
        if p.get('tie_start'):
            ties += '<tie type="start"/>'
        notations = ''
        if p.get('tie_stop') or p.get('tie_start'):
            tied = ('<tied type="stop"/>' if p.get('tie_stop') else '') + \
                   ('<tied type="start"/>' if p.get('tie_start') else '')
            notations = f'<notations>{tied}</notations>'
        return [f'{indent}<note><pitch><step>{step}</step>{alt}<octave>{octv}</octave></pitch>'
                f'<duration>{p["dur"]}</duration>{ties}<voice>1</voice><type>{t}</type>{extra}{beams}{notations}</note>']

    def to_musicxml(self):
        out = []
        out.append('<?xml version="1.0" encoding="UTF-8"?>')
        out.append('<score-partwise version="3.1">')
        out.append(f'  <work><work-title>{self._esc(self.title)}</work-title></work>')
        out.append('  <part-list><score-part id="P1"><part-name>Bass</part-name></score-part></part-list>')
        out.append('  <part id="P1">')
        first = True
        prev_meter = None
        for mi, m in enumerate(self.measures, 1):
            out.append(f'    <measure number="{mi}">')
            cur_meter = m.get('meter') or (self.beats, self.beat_type)
            if first:
                out.append('      <attributes>')
                out.append(f'        <divisions>{DIV}</divisions>')
                out.append(f'        <key><fifths>{self.key_fifths}</fifths><mode>{self.mode}</mode></key>')
                out.append(f'        <time><beats>{cur_meter[0]}</beats><beat-type>{cur_meter[1]}</beat-type></time>')
                out.append('        <clef><sign>F</sign><line>4</line></clef>')
                # 贝斯记谱:written = sounding + 12,声明八度移位让播放软件发出真实音高
                out.append('        <transpose><diatonic>0</diatonic><chromatic>0</chromatic><octave-change>-1</octave-change></transpose>')
                out.append('      </attributes>')
                prev_meter = cur_meter
                # verovio stacks later directions on top: emit bottom lines first, title last
                # each line is a separate direction — long lines get clipped to the first measure
                lines2 = []
                if self.tempo or self.tempo_words:
                    tt = f'Tempo {self.tempo}' if self.tempo else ''
                    if self.tempo_words:
                        tt = (tt + ', ' + self.tempo_words).strip(', ')
                    lines2.append(tt)
                if self.subtitle:
                    lines2.append(self.subtitle)
                for ln in lines2:
                    out.append('      <direction placement="above"><direction-type>')
                    out.append(f'        <words font-size="10">{self._esc(ln)}</words>')
                    out.append('      </direction-type></direction>')
                out.append('      <direction placement="above"><direction-type>')
                out.append(f'        <words font-size="15" font-weight="bold">{self._esc(self.title)}</words>')
                out.append('      </direction-type></direction>')
                first = False
            elif cur_meter != prev_meter:
                out.append('      <attributes>')
                out.append(f'        <time><beats>{cur_meter[0]}</beats><beat-type>{cur_meter[1]}</beat-type></time>')
                out.append('      </attributes>')
                prev_meter = cur_meter
            if m['word']:
                out.append('      <direction placement="above"><direction-type>')
                out.append(f'        <words font-weight="bold" font-size="12">{self._esc(m["word"])}</words>')
                out.append('      </direction-type></direction>')
            pieces = self._add_beams(self._measure_pieces(m))
            for p in pieces:
                out.extend(self._piece_xml(p))
            out.append('    </measure>')
        out.append('  </part>')
        out.append('</score-partwise>')
        return '\n'.join(out)

    def save(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_musicxml())
        return path
