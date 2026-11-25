# fuzzyscore

**给人类和 AI agent 用的"模糊线索"贝斯谱生成器。**

冷门歌曲没有官方谱。你实际能找到的只有一堆不完美的线索:歌词上方手打的和弦谱、论坛抓下来的 ASCII 四线谱、音频转 MIDI 服务吐出的粗糙 MIDI。fuzzyscore 就是把这些模糊线索调和成一套干净贝斯练习包的中间层:

- **MusicXML**(MuseScore 直接打开),
- **五线谱+TAB 合排 PDF**(LilyPond,带段落标记),
- **带节奏行的 ASCII 四线谱** —— 三者出自同一数据模型,永不打架。

差异化在**和弦谱先验**:几十年前有人手打在歌词上面的那个和弦走向,是一张免费的高质量和声地图。当粗糙的 MIDI 转录在小节里弹出和弦外音时,fuzzyscore 把它弯到最近的和弦内音——并且打印完整的修改日志,没有任何"悄悄改对"。

纯标准库 Python,零运行时依赖——刻意为之,方便 AI agent 通读、审计、直接 vendor 整个代码库。

## 快速上手

```
pip install -e .            # 或者不装:PYTHONPATH=src python3 -m fuzzyscore.cli --help
fuzzyscore demo out/        # 60 秒看完整个流程
```

demo 会合成一首"冷门歌"(Night Walk:和弦谱 + 故意带错音/键盘串音的 MIDI),然后跑完整管线:量化 → 和弦先验纠错(带日志)→ MusicXML → ASCII 谱 → 审计 → PDF。

LilyPond(渲染 PDF 用,可选):把[官方 tarball](https://lilypond.org/download.html) 解压到 `./lilypond/`,或设 `FUZZYSCORE_LILYPOND=/path/bin/lilypond`。

## CLI 一览

```
fuzzyscore tab2score IN.txt OUT.musicxml   # 比例 ASCII 谱 → 五线谱数据
fuzzyscore chords CHART.txt --list         # 和弦谱 → 逐小节和声地图
fuzzyscore midi-grid SONG.mid              # BPM 估计 + 每小节音高画像
fuzzyscore build SONG.mid CHART.txt OUT    # 量化 + 先验纠错(打印日志)
fuzzyscore tab IN.musicxml OUT.txt         # ASCII 谱(带 R 节奏行)
fuzzyscore render IN.musicxml OUT_BASE     # LilyPond 五线谱+TAB 合排 PDF
fuzzyscore audit IN.musicxml               # 逐小节时值审计
```

## 设计约定( agent 必读)

- 时值单位 = **16 分音符**(MusicXML divisions=4)。
- Score 里的音名是**实际演奏音高**(`E1` = 低音 E,MIDI 28);记谱写 +1 八度,XML 里 `<transpose><octave-change>-1</octave-change>` 保证 MIDI 回放音高正确。
- 小节元组第 3 位是延音标志:`('B1', 12, 't')` 延到下一小节,`('B1', 4, 'T')` 收束。
- `Score.meter(7, 4)` 中途换拍号(15/8 ↔ 4/4)。
- `Score.section('Chorus')` → PDF 排练记号 + ASCII 谱 `[Chorus]` 标签。

完整 agent 工作流见 [PLAYBOOK.md](PLAYBOOK.md);背景与路线图见 [README.md](README.md)。MIT 协议,见 [LICENSE](LICENSE)。
