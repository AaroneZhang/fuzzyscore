"""fuzzyscore.chordchart — parse human chord sheets (the first fuzzy clue).

Cold songs online usually have no tab at all — only a chord sheet somebody
typed above the lyrics.  That sheet is a free, high-quality harmonic prior:
it tells you the progression, the section structure and which pitch classes
are legal in each bar.  This module parses the common shapes:

    [Verse]                (Chorus)                chorus:
    Bm   F#m               Bm - F#m                | Bm | F#m D |
    Bm(2) E  A             (repeat chords found above lyric lines)
    Em7  A7  Dmaj7  Bbdim

Return value: a :class:`Chart` whose ``flat_bars()`` yields one entry per
bar: ``(section_name, chord_symbol, root_pc, safe_pcs)``.
"""
import re

NOTE_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}

CHORD_RE = re.compile(
    r'^([A-G])([#b])?'
    r'(maj|min|m|M|-|\+|dim|aug|sus|add)?'
    r'([0-9]*(?:sus[24]|add[0-9]+|\([^)]*\))*)?$'
)

# intervals (semitones above root) considered "safe" for a bass line
QUAL_TONES = {
    '': (0, 4, 7),
    'maj': (0, 4, 7), 'M': (0, 4, 7),
    'm': (0, 3, 7), 'min': (0, 3, 7), '-': (0, 3, 7),
    '7': (0, 4, 7, 10), 'maj7': (0, 4, 7, 11), 'M7': (0, 4, 7, 11),
    'm7': (0, 3, 7, 10), 'min7': (0, 3, 7, 10),
    'dim': (0, 3, 6), 'aug': (0, 4, 8), '+': (0, 4, 8),
    'sus2': (0, 2, 7), 'sus4': (0, 5, 7), 'sus': (0, 5, 7),
}


def parse_chord(token):
    """'Bbm7' -> ('Bb', 'm7', root_pc, safe_pcs)  or None if not a chord."""
    m = CHORD_RE.match(token)
    if not m:
        return None
    root = m.group(1) + (m.group(2) or '')
    pc = (NOTE_PC[root[0]] + (1 if root.endswith('#') else -1 if root.endswith('b') else 0)) % 12
    qual = (m.group(3) or '') + (m.group(4) or '')
    # normalize the messy middle ('m7', 'min7', '-7' ...)
    q = qual
    for cand in ('maj7', 'M7', 'min7', 'm7', 'min', 'maj', 'dim', 'aug', 'sus2', 'sus4', 'sus', 'add', 'm', 'M', '-', '7'):
        if q.startswith(cand):
            q = cand
            break
    else:
        q = ''
    if q == '-':
        q = 'm'
    if q == 'min':
        q = 'm'
    tones = QUAL_TONES.get(q, QUAL_TONES[''])
    pcs = {(pc + t) % 12 for t in tones}
    return root, qual, pc, pcs


def _line_chords(line):
    """Extract chord tokens from one line (ignoring lyric words)."""
    out = []
    for tok in re.findall(r'[A-G][#b]?(?:maj|min|m|M|dim|aug|sus|add)?[0-9()susadd]*', line):
        c = parse_chord(tok)
        if c:
            out.append((tok,) + c)
    return out


SECTION_RE = re.compile(r'^[\[\(]?\s*(intro|verse|pre-?chorus|chorus|bridge|solo|outro|coda|hook|interlude|refrain)[^\]\)]*[\]\)]?:?\s*$',
                        re.IGNORECASE)


class Chart:
    def __init__(self):
        self.sections = []  # (name, [(symbol, root, qual, root_pc, safe_pcs, bars)])

    def flat_bars(self):
        """-> [(section_name, symbol, root_pc, safe_pcs)] one entry per bar."""
        out = []
        for name, chords in self.sections:
            for sym, root, qual, pc, pcs, bars in chords:
                out.extend([(name, sym, pc, pcs)] * bars)
        return out

    def section_names(self):
        seen = []
        for name, _ in self.sections:
            if name not in seen:
                seen.append(name)
        return seen


def parse_chord_sheet(text):
    """Parse a chord sheet -> :class:`Chart`.

    Recognition rules, in order:
    1. A line that *is* a section label (``[Chorus]``, ``(chorus):`` ...) sets
       the current section name.
    2. A line that is mostly chord tokens (>= half of its whitespace-separated
       tokens parse as chords, or it uses ``| Bm |`` bar format) is a chord
       line: its chords are appended, one bar each (``Bm(2)``/``Bm*2`` = 2 bars).
    3. Anything else (lyrics, noise) is skipped.
    """
    chart = Chart()
    cur_name = 'Part'
    cur = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        sm = SECTION_RE.match(line)
        if sm:
            if cur:
                chart.sections.append((cur_name, cur))
                cur = []
            cur_name = sm.group(1).capitalize()
            cur_name = {'Pre-chorus': 'Pre-Chorus'}.get(cur_name, cur_name)
            continue
        # bar format: | Bm | F#m D |
        if '|' in line:
            toks = [t for t in re.split(r'[|]', line) if t.strip()]
            n = 0
            for cell in toks:
                for tok in cell.split():
                    c = parse_chord(tok)
                    if not c:
                        continue
                    bars = 1
                    mm = re.match(r'^(.*)[(\*](\d+)\)?$', tok)
                    if mm:
                        base = parse_chord(mm.group(1))
                        if base:
                            c = base
                            tok = mm.group(1)
                            bars = int(mm.group(2))
                    cur.append((tok, c[0], c[1], c[2], c[3], bars))
                    n += bars
            if n:
                continue
        toks = line.split()
        if not toks:
            continue
        hits = []
        for tok in toks:
            mm = re.match(r'^([A-G][#b]?(?:maj|min|m|M|dim|aug|sus|add)?[0-9]*)[(\*](\d+)\)?$', tok)
            bars = 1
            if mm:
                tok = mm.group(1)
                bars = int(mm.group(2))
            c = parse_chord(tok)
            if c:
                hits.append((tok, c[0], c[1], c[2], c[3], bars))
        # chord line = at least half the tokens are chords (chords-above-lyrics)
        if len(hits) >= max(1, len(toks) // 2):
            cur.extend(hits)
    if cur:
        chart.sections.append((cur_name, cur))
    return chart
