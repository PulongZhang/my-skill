---
name: running-song-maker
description: "用于把用户提供的歌曲制作成固定步频的跑步音乐。凡是用户要求歌曲变速不变调、保持人声自然、把音乐调整到 90/95 BPM 或其他 5 的倍数、按 180/190 步频叠加节拍器、让 click 与歌曲拍点全程同步、制作跑步歌单或检查跑步音乐节拍和响度时，都应使用本 Skill。使用内置木质 click、确定性 Python 脚本和 Rubber Band/FFmpeg 完成分析、变速、对拍、混音与验收。"
compatibility: "需要 uv；高质量成品优先需要 Rubber Band CLI，压缩格式输入输出需要 FFmpeg。"
---

# 跑步歌曲制作器

## 核心目标

把用户提供的歌曲制作成固定步频跑步音乐，同时满足：

- 只改变播放速度，不改变音高；使用 Rubber Band R3/Finer 离线模式保护人声尾音、颤音和立体声相位，使人声保持自然。音高比例固定为 `1.0`，无需启用仅供移调使用的 formant 选项。
- 音乐目标 BPM 尽量取 5 的倍数，默认优先在 `90` 和 `95 BPM` 中选择变速幅度较小者。
- 节拍器每半拍响一次：`click 频率 = 音乐 BPM × 2`，即 `90 BPM → 180 次/分钟`、`95 BPM → 190 次/分钟`。
- 节拍器与最终音乐拍点使用同一时间网格，不能只对齐开头后任其逐渐漂移。
- 所有 click 等音量、无重音，不区分奇偶位或小节强拍。
- 节拍器电平全程固定；安静段落中允许其自然浮出，不做自动闪避、动态跟随或逐段调音量。
- 默认让 click 峰值约比音乐全曲平均 RMS 高 `16 dB`；音乐过响时只降低音乐，不提高 click 或压缩人声。

处理前按需读取 `references/audio-processing-spec.md`；需要解释报告字段或判断成品是否通过时读取 `references/output-report-format.md`。

## 固定素材

使用：

```text
assets/running_wood_click_580hz_soft6ms.wav
```

这是本 Skill 的固定节拍器采样，具有木质、非谐波 click 听感。不要临时改用正弦波、系统蜂鸣声、鼓组、强弱拍不同的采样，也不要对 click 做时间拉伸。脚本会在混音阶段将其重采样到歌曲采样率，并统一校准到固定峰值。

## Python 与外部运行时

所有 Python 环境、依赖和脚本必须通过 uv 管理和运行：

```bash
uv sync --locked --project ~/.claude/skills/running-song-maker
uv run --project ~/.claude/skills/running-song-maker python ~/.claude/skills/running-song-maker/scripts/make_running_song.py --help
```

不要使用裸 `python`、`pip install`、Conda 或未记录的全局 Python 包。

外部音频程序不属于 Python 环境：

- **Rubber Band CLI**：高质量变速不变调的首选，尤其适合含人声歌曲和存在轻微速度漂移的歌曲。
- **FFmpeg**：用于 MP3、M4A、AAC 等格式解码/编码，也可在节奏稳定且只需全局变速时作为 `atempo` 后备方案。

如果 Rubber Band 不可用，不要把低质量 Python 相位声码器当作正式人声成品。可以使用 FFmpeg `atempo` 处理幅度较小的全局变速，但必须在报告中标明后备引擎；存在局部节拍漂移时应停止并说明需要 Rubber Band。

## 工作流程

### 1. 检查输入和用户目标

确认：

- 输入歌曲路径存在；
- 输出路径由用户指定，或使用明确的派生文件名；
- 用户是否明确指定目标 BPM；
- 用户是否提供首个可靠正拍时间；
- 用户是否允许超过默认阈值的大幅变速。

不要覆盖用户原始歌曲。默认输出无损 WAV 主文件；用户要求 MP3、M4A 等压缩格式时，再通过 FFmpeg 编码一次。

### 2. 分析原曲

先运行分析模式：

```bash
uv run --project ~/.claude/skills/running-song-maker \
  python ~/.claude/skills/running-song-maker/scripts/make_running_song.py \
  --input "/path/to/song.mp3" \
  --analyze-only
```

脚本会：

- 从打击乐 onset 包络估计 BPM；
- 处理 `45/90/180`、`47.5/95/190` 等半速与倍速歧义；
- 检测连续四分音符拍点；
- 拟合拍点网格并计算局部速度漂移；
- 在 `90/95 BPM` 中推荐变速比例较小者；
- 输出人声自然度相关的变速幅度风险。

自动拍点置信度低时，不要静默继续。请用户试听确认原曲 BPM，提供 `--first-beat` 秒数修正相位，并配合 `--allow-low-confidence` 确认分析结果后继续。

### 3. 选择目标 BPM

默认 `--target-bpm auto`：

- 在 `90` 和 `95 BPM` 中选择与原曲标准化 BPM 比例更接近者；
- 两者距离相同时优先 `95 BPM`；
- 用户可明确指定其他正数 BPM，通常应优先使用 5 的倍数。

变速幅度建议：

- `≤5%`：通常可保持非常自然；
- `5%～8%`：大多数歌曲仍可接受；
- `8%～12%`：需要重点试听人声；
- `>12%`：默认停止，只有用户明确接受后才使用 `--allow-large-stretch`。

注意：即使目标 BPM 是用户自己指定的（例如明确要求把 120 BPM 压到 90 BPM），也不能把这种指定当作已经隐式接受人声风险。用户指定目标只说明他们想要这个速度，不代表他们知道大幅变速会损伤人声。只要变速幅度超过 `12%`，必须先向用户说明预期的人声伪影并取得显式确认，才能继续；确认前不生成成品，也不要替用户推断“可视为接受”。

人声自然度优先于为了得到 90/95 BPM 而进行不必要的大幅拉伸。

### 4. 选择节拍校正模式

默认 `--tempo-mode auto`：

- 原曲拍点已接近恒定网格时，整首只做一次全局时间拉伸，以保持人声最自然。
- 检测到会造成明显首尾漂移的局部速度变化时，使用 Rubber Band time map 做平滑非均匀拉伸。
- 非均匀模式以多拍锚点形成连续时间映射，不逐拍切割、拼接或交叉淡化人声。
- 若只能使用 FFmpeg 且原曲存在明显漂移，停止并报告，不生成假装全程对齐的成品。

用户明确指定 `--tempo-mode global` 时允许只做全局变速；报告必须保留预计 P95 对齐误差。`--tempo-mode strict` 强制使用 Rubber Band 时间映射。

### 5. 生成成品

典型命令：

```bash
uv run --project ~/.claude/skills/running-song-maker \
  python ~/.claude/skills/running-song-maker/scripts/make_running_song.py \
  --input "/path/to/song.mp3" \
  --output "/path/to/song_running_95bpm.wav" \
  --target-bpm 95
```

自动选择目标 BPM：

```bash
uv run --project ~/.claude/skills/running-song-maker \
  python ~/.claude/skills/running-song-maker/scripts/make_running_song.py \
  --input "/path/to/song.wav" \
  --output "/path/to/song_running.wav" \
  --target-bpm auto
```

人工指定首个正拍：

```bash
uv run --project ~/.claude/skills/running-song-maker \
  python ~/.claude/skills/running-song-maker/scripts/make_running_song.py \
  --input "/path/to/song.wav" \
  --output "/path/to/song_running_90bpm.wav" \
  --target-bpm 90 \
  --first-beat 7.420
```

脚本先处理音乐，再基于最终时间轴生成 click，最后混音。不要先把 click 混入原曲后一起拉伸，因为那会改变固定采样的攻击和音色。

### 6. 检查报告

默认在输出音频旁生成：

```text
<输出文件名>.report.json
```

检查：

- 原曲 BPM、目标 BPM 和变速百分比；
- 使用的变速引擎和节拍模式；
- click 实际频率与间隔；
- 音乐 RMS、click 峰值及两者差值；
- 奇偶 click 幅度比；
- 拍点 P50/P95 误差与预计首尾漂移；
- 输出峰值、是否削波、采样率和声道数；
- 是否触发大幅变速、低置信度或后备引擎警告。

报告不通过时不要仅凭文件已生成就宣称完成。

## 响度规则

默认参数：

```text
click 峰值：-6 dBFS
click 峰值 - 音乐平均 RMS：16 dB
目标音乐平均 RMS：约 -22 dBFS
输出峰值上限：-1 dBFS
```

执行原则：

1. 将固定 click 采样统一校准到 `-6 dBFS`。
2. 测量变速后、混音前音乐的全曲 RMS。
3. 音乐高于 `-22 dBFS` 时整体衰减；默认不提升较安静的音乐。
4. 如果叠加后可能削波，继续只降低音乐，保持 click 固定。
5. 不使用 limiter、自动增益、ducking、奇偶重音或段落自动化。

用户明确给出其他电平时，可通过脚本参数覆盖，但仍保持固定 click 和全程不调原则。

当用户要求“越响越好”、强压限幅或其他可能破坏固定关系的处理时，回复中必须明确重述完整响度关系，而不能只给输出峰值：默认 click 峰值约 `-6 dBFS`、音乐平均 RMS 上限约 `-22 dBFS`，两者相差约 `16 dB`，成品峰值不高于约 `-1 dBFS`。拒绝无限增益、limiter、压缩人声和强弱交替；有削波风险时只继续降低音乐。

输入歌曲路径存在且用户已提供时，再展示该歌曲的实际处理命令；若歌曲路径尚不存在，应明确说明当前只是处理计划、尚未执行音频分析或生成成品，不要虚构分析结果。

## 输出命名

不指定 `--output` 时，成品默认命名为：

```text
<原歌曲名>(<目标bpm>bpm).wav
```

示例：

- `Blinding Lights.m4a` → `Blinding Lights(90bpm).wav`
- `Die For You.flac` → `Die For You(90bpm).wav`
- `Starboy.mp3` → `Starboy(95bpm).wav`

生成文件与输入同目录。`--output` 明确指定时使用指定路径。回复中报告成品路径时使用实际文件名。

## 输出与回复

完成后向用户报告：

- 最终音频绝对路径；
- JSON 报告绝对路径；
- 原曲 BPM、目标 BPM、最终步频和变速比例；
- 实际使用的变速引擎；
- 人声风险提示或后备引擎提示；
- 对齐、响度和削波检查是否通过。

不要声称已经试听人声；只能报告算法、测量结果和实际执行的验证。用户提供歌曲后，应邀请用户重点试听主歌、持续长音、副歌和最大局部拉伸区域。

## 自检清单

输出前逐项检查：

- 原始歌曲未被覆盖。
- Python 命令全部通过 uv 执行。
- 音高偏移参数为零，未采用改变采样率的伪变速。
- 人声歌曲优先使用 Rubber Band R3/Finer 高质量离线模式；立体声中心人声默认启用 `--centre-focus`，音高保持 `1.0`。
- click 使用固定资产，未被时间拉伸。
- click 频率等于目标音乐 BPM 的两倍。
- 每个 click 等音量，奇偶位幅度比接近 `1.00`。
- 节拍器全程固定，不存在强拍重音、ducking 或逐段音量调整。
- 音乐过响时降低音乐，不通过压缩人声解决。
- 自动模式已检查局部速度漂移，不能只验证开头。
- 输出没有削波，报告文件能够解析。
- 压缩输出已重新解码并检查是否出现编码器延迟或削波。
- 最终回复包含音频和报告的绝对路径。
