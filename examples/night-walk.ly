\version "2.26.0"
\language "english"
\header {
  title = "Night Walk (demo)"
  subtitle = "fuzzyscore demo: chord sheet as harmonic prior"
  composer = "Bass"
}

staffMusic = {
  \key b \minor
  \tempo 4 = 120
  \time 4/4
  \mark \markup \bold "Verse"
  b,4 fs4 b,4 b8 r8
  fs,4 cs4 fs,4 fs8 r8
  b,4 fs4 b,4 b8 r8
  fs,4 cs4 fs,4 fs8 r8
  \mark \markup \bold "Pre-Chorus"
  b,4 fs4 b,4 b8 r8
  d4 a4 d4 d'8 r8
  e4 b4 e4 e'8 r8
  a,4 e4 a,4 a8 r8
  \mark \markup \bold "Chorus"
  cs4 gs4 cs4 cs'8 r8
  d4. r8 d4 d'8 r8
  e4 b4 e4 e'8 r8
  a,4 e4 a,4 a8 r8
  a,4 e4 a,4 a8 r8
  e4 b4 e4 e'8 r8
  fs,4 cs4 fs,4 fs8 r8
  cs4 gs4 cs4 cs'8 r8
}

tabMusic = {
  \key b \minor
  \time 4/4
  b,4 fs4 b,4 b8 r8
  fs,4 cs4 fs,4 fs8 r8
  b,4 fs4 b,4 b8 r8
  fs,4 cs4 fs,4 fs8 r8
  b,4 fs4 b,4 b8 r8
  d4 a4 d4 d'8 r8
  e4 b4 e4 e'8 r8
  a,4 e4 a,4 a8 r8
  cs4 gs4 cs4 cs'8 r8
  d4. r8 d4 d'8 r8
  e4 b4 e4 e'8 r8
  a,4 e4 a,4 a8 r8
  a,4 e4 a,4 a8 r8
  e4 b4 e4 e'8 r8
  fs,4 cs4 fs,4 fs8 r8
  cs4 gs4 cs4 cs'8 r8
}

\score {
  \new StaffGroup <<
    \new Staff { \clef bass \staffMusic }
    \new TabStaff \with { stringTunings = #bass-tuning } { \transpose c c, \tabMusic }
  >>
  \layout { indent = #0 }
}
\paper { #(set-paper-size "a4") left-margin = 12 right-margin = 12 oddFooterMarkup = ##f evenFooterMarkup = ##f }
