"""fuzzyscore — a fuzzy-clue bass score generator for human/AI agents.

Cold songs have no official sheet music.  What you *can* find is a pile of
imperfect clues: a chord sheet typed above lyrics, an ASCII tab scraped off
a forum, a rough MIDI from an audio-to-MIDI service, maybe the recording
itself.  fuzzyscore is the reconciliation layer that turns those fuzzy
clues into a clean practice pack: MusicXML, a notation+TAB PDF (LilyPond),
and an ASCII tab — all generated from one data model.

The library is pure standard-library Python by design, so an AI agent can
read, audit and vendor it easily.
"""
__version__ = '0.1.0'

from .notation import Score, parse_tab_block
from .chordchart import parse_chord_sheet
from .midiio import parse_midi, write_midi
from . import quantize, texttab, lilypond

__all__ = ['Score', 'parse_tab_block', 'parse_chord_sheet',
           'parse_midi', 'write_midi', 'quantize', 'texttab', 'lilypond']
