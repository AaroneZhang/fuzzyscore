"""fuzzyscore.midiio — pure-stdlib MIDI reader + minimal writer.

Reader returns absolute seconds (tempo-map aware).  Writer emits a
type-0 single-track file, enough for demos/tests and for agents that
want to synthesize fixture audio-transcriptions.
"""
import struct


def _varlen(data, pos):
    val = 0
    while True:
        b = data[pos]
        pos += 1
        val = (val << 7) | (b & 0x7F)
        if not b & 0x80:
            return val, pos


def parse_midi(path):
    """-> {'format','ntrks','division','notes':[(start_sec,end_sec,pitch,vel)],
    'bends':[(tick,val)],'tempos':[(tick,us_per_quarter)]}"""
    data = open(path, 'rb').read()
    assert data[:4] == b'MThd', 'not a midi file'
    hdr_len = struct.unpack('>I', data[4:8])[0]
    fmt, ntrks, division = struct.unpack('>HHH', data[8:14])
    pos = 8 + hdr_len
    tempos = []   # (tick, us_per_quarter)
    notes = []    # (start_tick, end_tick, pitch, vel, track)
    bends = []
    cur_us = 500000
    tempos.append((0, cur_us))
    for t in range(ntrks):
        assert data[pos:pos + 4] == b'MTrk', f'bad track {t}'
        tlen = struct.unpack('>I', data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + tlen]
        pos += 8 + tlen
        tick = 0
        i = 0
        run = None
        on = {}
        while i < len(body):
            delta, i = _varlen(body, i)
            tick += delta
            b = body[i]
            if b == 0xFF:  # meta
                mtype = body[i + 1]
                ln, j = _varlen(body, i + 2)
                if mtype == 0x51 and ln == 3:
                    cur_us = (body[j] << 16) | (body[j + 1] << 8) | body[j + 2]
                    tempos.append((tick, cur_us))
                i = j + ln
            elif b in (0xF0, 0xF7):  # sysex
                ln, j = _varlen(body, i + 1)
                i = j + ln
            else:
                if b & 0x80:
                    run = b
                    i += 1
                ev = run
                typ = ev & 0xF0
                if typ in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                    p1, p2 = body[i], body[i + 1]
                    i += 2
                    if typ == 0x90 and p2 > 0:
                        on.setdefault((ev & 0x0F, p1), []).append((tick, p2))
                    elif typ == 0x80 or (typ == 0x90 and p2 == 0):
                        k = (ev & 0x0F, p1)
                        if on.get(k):
                            s, v = on[k].pop(0)
                            notes.append((s, tick, p1, v, t))
                    elif typ == 0xE0:
                        bends.append((tick, (p2 << 7) | p1))
                elif typ in (0xC0, 0xD0):
                    i += 1
    tempos.sort()

    def tick2sec(tick):
        sec = 0.0
        last_t = 0
        us = tempos[0][1]
        for tt, u in tempos:
            if tt >= tick:
                break
            if tt > last_t:
                sec += (min(tt, tick) - last_t) * us / division / 1e6
                last_t = tt
                us = u
        sec += (tick - last_t) * us / division / 1e6
        return sec

    out = [(tick2sec(s), tick2sec(e), p, v) for s, e, p, v, t in notes]
    out.sort()
    return {'format': fmt, 'ntrks': ntrks, 'division': division,
            'notes': out, 'bends': bends, 'tempos': tempos}


# ---------------- minimal writer (type 0) ----------------

def _vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def write_midi(path, notes, bpm=120.0, division=480):
    """notes: [(start_sec, end_sec, pitch, vel)] -> single-track MIDI."""
    us_per_q = int(round(60e6 / bpm))
    body = bytearray()
    # tempo meta at tick 0
    body += _vlq(0) + b'\xFF\x51\x03' + bytes([(us_per_q >> 16) & 0xFF,
                                               (us_per_q >> 8) & 0xFF, us_per_q & 0xFF])
    evs = []
    for s, e, p, v in notes:
        t0 = int(round(s * bpm / 60 * division))
        t1 = max(t0 + 1, int(round(e * bpm / 60 * division)))
        evs.append((t0, 0x90, p, v))
        evs.append((t1, 0x80, p, 0))
    evs.sort(key=lambda x: (x[0], x[1]))
    tick = 0
    for t, typ, p, v in evs:
        body += _vlq(t - tick) + bytes([typ, p, v])
        tick = t
    body += _vlq(0) + b'\xFF\x2F\x00'
    hdr = b'MThd' + struct.pack('>IHHH', 6, 0, 1, division)
    trk = b'MTrk' + struct.pack('>I', len(body)) + bytes(body)
    with open(path, 'wb') as f:
        f.write(hdr + trk)
    return path
