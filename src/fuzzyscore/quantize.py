"""fuzzyscore.quantize — rough MIDI -> 16th-note grid -> bass Score.

This is the reconciliation step where fuzzy clues meet:

1. ``estimate_bpm`` — autocorrelate the onset signal (grid-free, so a
   wrong global tempo guess cannot poison everything).
2. ``fit_grid`` — snap onsets to a 16th-note grid (windowed re-fit keeps
   long songs from drifting).
3. ``collapse`` — keep the lowest pitch per slot (bass is monophonic),
   drop contained short events (kick residue / ghost leakage), clip
   durations at the next onset.
4. ``snap_to_chords`` — *the* differentiator: use a parsed chord sheet as
   a harmonic prior.  Pitches that are foreign to the current bar's chord
   get bent to the nearest chord tone (or dropped); every edit is logged
   so the agent (or human) can review what the prior changed.
5. ``slots_to_score`` — build the score: cross-bar ties, register cap
   (keyboard bleed above the cap becomes rests), first-bar cleanup,
   section rehearsal marks.
"""
from .notation import Score

PCN = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def pc_of(midi):
    return PCN[midi % 12] + str(midi // 12 - 1)


# ---------------- 1. tempo ----------------

def estimate_bpm(notes, lo=60.0, hi=185.0):
    """Autocorrelate the onset indicator.  The strongest lag is read as two
    beats first, then one, then four (robust for backbeat-heavy material).
    Returns bpm or None."""
    if not notes:
        return None
    end = max(n[1] for n in notes)
    step = 0.01
    n = int(end / step) + 1
    ind = [0.0] * n
    for s, e, p, v in notes:
        ind[min(int(s / step), n - 1)] += 1.0
    # a 2-beat lag for bpm in [lo, hi] spans 2*60/hi .. 2*60/lo seconds
    lag_lo, lag_hi = int(2 * 60.0 / hi / step), int(2 * 60.0 / lo / step) + 1
    best = None
    for lag in range(max(1, lag_lo), min(lag_hi, n // 2)):
        acc = sum(ind[i] * ind[i + lag] for i in range(n - lag))
        if best is None or acc > best[1]:
            best = (lag, acc)
    if not best or best[1] <= 0:
        return None
    lag = best[0] * step
    for bpm in (120.0 / lag, 60.0 / lag, 240.0 / lag):
        if lo <= bpm <= hi:
            return round(bpm, 1)
    return None


# ---------------- 2-3. grid ----------------

def fit_grid(notes, bpm, origin=None, window_bars=24):
    """Snap note times onto a 16th grid -> {slot: [(pitch, dur_slots, vel)]}.

    ``origin`` defaults to the first onset.  Every ``window_bars`` bars the
    local offset is re-fit (and added back globally), so tempo drift or a
    slightly-wrong bpm cannot accumulate.
    """
    s16 = 60.0 / bpm / 4
    if origin is None:
        origin = notes[0][0] if notes else 0.0
    slots = {}
    base_slot = 0
    t0 = origin
    while t0 <= notes[-1][1]:
        t1 = min(t0 + window_bars * 16 * s16, notes[-1][1] + 1e-9)
        win = [nt for nt in notes if nt[0] >= t0 - 1e-9 and nt[0] < t1]
        if win:
            off = min(nt[0] for nt in win)
            delta = round((off - t0) / s16)
            base_slot += delta
        for s, e, p, v in win:
            k = base_slot + round((s - t0) / s16)
            d = max(1, round((e - s) / s16))
            slots.setdefault(k, []).append((p, d, v))
        if t1 >= notes[-1][1] + 1e-9:
            break
        t0 = t1
    return slots


def collapse(slots, max_dur=32, low=None, high=None, report=None):
    """Monophonic cleanup.  -> {slot: (pitch, dur_slots, vel)}.

    ``low``/``high`` filter the register *before* anything else, so keyboard
    bleed above the bass range cannot clip a real bass note's duration.  The
    old contained-note heuristic also deleted genuinely wrong low notes (and
    real octave doublings) before ``snap_to_chords`` could log them; it is
    deliberately gone — the register filter plus the chord prior now own that
    decision, visibly.
    """
    filtered = 0
    if low is not None or high is not None:
        kept = {}
        for k, evs in slots.items():
            keep = [(p, d, v) for p, d, v in evs
                    if (low is None or p >= low) and (high is None or p <= high)]
            filtered += len(evs) - len(keep)
            if keep:
                kept[k] = keep
        slots = kept
    onsets = sorted(slots)
    out = {}
    for i, k in enumerate(onsets):
        p, d, v = min(slots[k], key=lambda x: x[0])  # bass takes the low note
        nxt = onsets[i + 1] if i + 1 < len(onsets) else k + d
        d = max(1, min(d, nxt - k, max_dur))
        out[k] = (p, d, v)
    if report is not None:
        report['register_filtered'] = filtered
    return out


def bar_profile(slots, nbars):
    """Per-bar pitch histogram — the agent reads this to label sections."""
    prof = {}
    for k, (p, d, v) in sorted(slots.items()):
        b = k // 16
        w = prof.setdefault(b, {})
        w[p] = w.get(p, 0) + d
    return [prof.get(b, {}) for b in range(nbars)]


# ---------------- 4. chord prior ----------------

def snap_to_chords(slots, chart_bars, max_bend=2):
    """Bend every note toward its bar's chord tones.  chart_bars: list of
    (section, symbol, root_pc, safe_pcs) — one entry per bar (may be shorter
    than the song; extra bars are left untouched).  Returns (new_slots, log).
    """
    log = []
    out = dict(slots)
    for k in sorted(out):
        b = k // 16
        if b >= len(chart_bars):
            continue
        _, sym, root_pc, pcs = chart_bars[b]
        p, d, v = out[k]
        pc = p % 12
        if pc in pcs:
            continue
        # bend to nearest chord tone, same octave or the one below
        cands = []
        for tone in pcs:
            for oct_shift in (0, -12):
                cand = p - pc + tone + oct_shift
                if abs(cand - p) <= max_bend:
                    cands.append(cand)
        if cands:
            newp = min(cands, key=lambda c: (abs(c - p), c))
            prev = max((kk for kk in out if kk < k), default=None)
            if (prev is not None and out[prev][0] == newp
                    and prev + out[prev][1] >= k):
                # The bend lands on the pitch already ringing: extend it
                # instead of producing a second attack / stutter.
                pp, pd, pv = out[prev]
                out[prev] = (pp, max(pd, k + d - prev), pv)
                log.append(f'bar {b + 1} slot {k}: {pc_of(p)} -> {pc_of(newp)} '
                           f'(toward {sym}; merged into sustaining note)')
                del out[k]
                continue
            log.append(f'bar {b + 1} slot {k}: {pc_of(p)} -> {pc_of(newp)} (toward {sym})')
            out[k] = (newp, d, v)
        else:
            log.append(f'bar {b + 1} slot {k}: {pc_of(p)} dropped (foreign to {sym})')
            del out[k]
    return out, log


# ---------------- 5. score ----------------

def slots_to_score(slots, title, key_fifths=2, mode='minor', tempo=120,
                   prefer='sharps', subtitle=None, sections=None,
                   low=26, high=60, drop_first_bar=False):
    """Grid -> Score.  ``sections``: {bar_number(1-based): label}.  Notes
    outside [low, high] are treated as bleed and become rests; cross-bar
    durations become ties; the final note is clipped, not spilled.

    ``drop_first_bar`` is opt-in: a pickup/lead-in bar is only sometimes
    disposable, so silently deleting bar 1 deleted real music in the bundled
    example.  Pass ``drop_first_bar=True`` only when the first bar is known to
    be a count-in."""
    S = Score(title, key_fifths, mode, beats=4, beat_type=4, tempo=tempo,
              tempo_words=f'Tempo {tempo}', prefer=prefer, subtitle=subtitle)
    clean = {k: v for k, v in slots.items() if low <= v[0] <= high}
    if drop_first_bar:
        for k in [k for k in clean if k < 16]:
            del clean[k]
    if not clean:
        return S
    nbars = max(clean) // 16 + 1
    carry = None
    for b in range(nbars):
        base = b * 16
        items = []
        k = base
        if carry:
            pn, rem = carry
            take = min(rem, 16)
            items.append((pn, take, 'T'))
            carry = (pn, rem - take) if rem > take else None
            k = base + take
        while k < base + 16:
            if k in clean:
                p, d, v = clean[k]
                end = k + d
                if end <= base + 16:
                    items.append((pc_of(p), end - k))
                    k = end
                elif b == nbars - 1:  # final note: fill the bar, don't spill
                    items.append((pc_of(p), base + 16 - k))
                    k = base + 16
                else:
                    items.append((pc_of(p), base + 16 - k, 't'))
                    carry = (pc_of(p), end - (base + 16))
                    k = base + 16
            else:
                nxt = next((kk for kk in sorted(clean) if kk > k), base + 16)
                end = min(nxt, base + 16)
                items.append((None, end - k))
                k = end
        if sections and (b + 1) in sections:
            S.section(sections[b + 1])
        S.bar(items)
    return S
