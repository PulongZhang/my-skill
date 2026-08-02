---
name: running-song-maker
description: "用于把用户提供的单首歌曲制作成固定步频的跑步音乐。凡是用户要求歌曲变速不变调、保持人声自然、调整到 90/95 BPM 或其他目标 BPM、按 180/190 步频叠加等音量节拍器、让 click 与歌曲拍点全程同步，或检查现有跑步音频的节拍和响度时，都应使用本 Skill。使用内置木质 click、确定性 Python 脚本和 Rubber Band/FFmpeg 完成分析、变速、对拍、混音与解码验收；批量生产回归由独立测试脚本完成。"
compatibility: "需要 uv；高质量严格时间映射需要 Rubber Band CLI；压缩格式输入输出需要 FFmpeg。"
---

# 跑步歌曲制作器

## 核心目标

把用户提供的单首歌曲制作成固定步频跑步音乐，同时满足：

- 只改变播放速度，不改变音高；优先使用 Rubber Band R3/Finer 离线模式保护人声尾音、颤音和立体声相位。音高比例固定为 `1.0`，不启用移调选项。
- 目标音乐 BPM 默认在 `90` 和 `95 BPM` 中选择变速比例较小者；用户可以明确指定其他正数 BPM。
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

这是本 Skill 的固定节拍器采样，具有木质、非谐波 click 听感。不要临时改用正弦波、系统蜂鸣声、鼓组、强弱拍不同的采样，也不要对 click 做时间拉伸。脚本只允许对它做高质量采样率转换和一次固定峰值校准。

## Python 与外部运行时

所有 Python 环境、依赖和脚本必须通过 uv 管理和运行：

```bash
uv sync --locked --project ~/.claude/skills/running-song-maker
uv run --project ~/.claude/skills/running-song-maker \
  python ~/.claude/skills/running-song-maker/scripts/make_running_song.py --help
```

不要使用裸 `python`、`pip install`、Conda 或未记录的全局 Python 包。

外部音频程序不属于 Python 环境：

- **Rubber Band CLI**：高质量全局变速和严格时间映射的首选，尤其适合含人声歌曲和存在轻微速度漂移的歌曲。
- **FFmpeg**：用于 MP3、M4A、AAC 等格式解码/编码，也可在节奏稳定且只需全局变速时作为 `atempo` 后备方案。

如果 Rubber Band 不可用，global 模式可以在小幅、恒定变速时使用 FFmpeg `atempo`，但报告必须标明后备引擎；strict 模式没有 Rubber Band CLI 时明确失败，不能把 FFmpeg 全局变速冒充严格时间映射。

## 工作流程

### 1. 检查输入和用户目标

确认：

- 输入歌曲和固定 click 资产存在；
- 输出、报告、输入和 click 路径互不相同；
- 用户是否明确指定目标 BPM；
- 用户是否提供首个可靠正拍时间；
- 用户是否明确允许超过默认变速风险阈值。

不要覆盖用户原始歌曲。未指定输出时，脚本默认在输入同目录生成 `<原歌曲名>(<目标bpm>bpm).wav`；显式报告路径仍然有效。`--overwrite` 不能绕过输入或 click 资产碰撞保护。

### 2. 分析原曲

先运行分析模式：

```bash
uv run --project ~/.claude/skills/running-song-maker \
  python ~/.claude/skills/running-song-maker/scripts/make_running_song.py \
  --input "/path/to/song.mp3" \
  --analyze-only
```

脚本会：

- 从打击乐 onset 包络估计源 BPM；
- 通过半速/倍速候选和网格证据处理 BPM 歧义；目标偏好不会反过来污染源 BPM 判断；
- 只把实际检测到的 onset 作为拍点观测，缺拍保留 musical ordinal 跳号；
- 拟合拍点网格并计算 P50、P95、首尾漂移和最大连续缺拍区间；
- 当观测覆盖不足或存在长缺拍区间时，auto 不把 censored observation 当作恒速证据，会降低置信度并优先选择 strict/要求确认；
- 在 `90/95 BPM` 中推荐变速比例较小者；
- 输出置信度、观测覆盖率、手工锚点状态和变速幅度风险。

自动拍点置信度低时，不要静默继续。请用户试听确认原曲 BPM，必要时提供 `--first-beat` 秒数修正相位，并配合 `--allow-low-confidence` 明确确认后继续。

### 3. 选择目标 BPM与变速风险

默认 `--target-bpm auto` 在 `90` 和 `95 BPM` 中选择相对变速比例较小者；两者比例距离相同时优先 `95 BPM`。目标 BPM 只在源 BPM 已由音频证据确定后参与选择。

变速幅度建议：

- `≤5%`：通常可保持非常自然；
- `5%～8%`：大多数歌曲仍可接受；
- `8%～12%`：需要重点试听人声；
- `>12%`：默认停止。

`--max-stretch-percent` 只能把阈值调低，不能把安全上限调高。超过有效阈值时，只有用户明确接受人声风险并使用 `--allow-large-stretch` 才能继续；用户指定目标 BPM 本身不等于风险确认。

### 4. 选择节拍校正模式

默认 `--tempo-mode auto`：

- 先用原曲真实拍点观测预测 global 变速后的对齐误差；
- 当预测 P95 大于 `25 ms` 或首尾漂移大于 `50 ms` 时选择 strict；
- 其他情况使用单次 global 变速，尽量减少人声处理；
- strict 使用按 musical ordinal 构建的平滑 Rubber Band time map，不逐拍切割、拼接或交叉淡化人声。

用户明确指定 `--tempo-mode global` 时允许强制 global，但报告会保留预计对齐误差并写入 warning。global 变速后，click 周期只在目标 BPM 附近拟合；手工 `--first-beat` 会锁定为最终输出相位。strict 模式以权威 anchor 和目标网格生成 click。

### 5. 生成成品

典型命令：

```bash
uv run --project ~/.claude/skills/running-song-maker \
  python ~/.claude/skills/running-song-maker/scripts/make_running_song.py \
  --input "/path/to/song.mp3" \
  --output "/path/to/song_running_95bpm.wav" \
  --target-bpm 95
```

脚本支持 `.wav`、`.flac`、`.mp3`、`.m4a`、`.aac` 和 `.opus`；未知扩展名会在处理前拒绝。MP3 和 Opus 明确输出为 `48 kHz`，其他格式沿用处理采样率；AAC 原始流的编码器 priming 使用更宽的 codec-aware 验收容差并在报告中记录。脚本先处理音乐，再基于最终时间轴生成 click，最后混音；不要先把 click 混入原曲后一起拉伸。

### 6. 检查报告

默认在输出音频旁生成：

```text
<输出文件名>.report.json
```

报告必须同时检查：

- 原曲 BPM、目标 BPM、步频和变速百分比；
- 实际引擎和 global/strict 模式；
- click 实际频率、间隔、峰值和奇偶比；
- 音乐 RMS、click 峰值及两者差值；
- 原曲拍点映射的 P50/P95 误差与预计首尾漂移；
- 重新解码后的采样率、声道、时长、最终峰值、编码延迟和尾部 padding；
- `acceptance.checks` 中每一项具名检查，以及顶层 `passed`。

顶层 `passed` 是所有适用自动检查的逻辑与。验收失败时仍保留输出和报告并返回退出码 `3`；参数、依赖或处理错误返回 `2`。报告不通过时不要仅凭文件已生成就宣称完成。

### 已有成品的只读回归

批量检查已有 WAV 时使用独立测试脚本，不把缺失的历史 engine、source BPM、stretch ratio 或 report 补写进成品目录：

```bash
uv run --project ~/.claude/skills/running-song-maker \
  python ~/.claude/skills/running-song-maker/tests/production_regression.py \
  --corpus "/path/to/running-wav-directory"
```

该脚本只写入仓库外的 `running-song-maker-workspace/` 数值结果，使用固定 click 模板测量 cadence、漏拍、P95、首尾漂移和奇偶比，并逐首执行 `--analyze-only`；它不会修改或复制音频。

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
3. 音乐高于目标 RMS 时整体衰减；不通过提高 click 或压缩人声来补偿。
4. 如果叠加后可能削波，继续只降低音乐，保持 click 固定。
5. 不使用 limiter、自动增益、ducking、奇偶重音或段落自动化。

## 输出命名和回复

不指定 `--output` 时：

```text
<原歌曲名>(<目标bpm>bpm).wav
```

例如 `song.flac` 目标 `92.5` 会生成 `song(92.5bpm).wav`。完成后报告实际音频路径、JSON 报告路径、源/目标 BPM、步频、变速比例、引擎、对齐/响度/峰值/编码验收结果和仍需用户试听的人声风险。

不要声称已经试听人声；只能报告算法、测量结果和实际执行的验证。用户应重点试听主歌、持续长音、副歌和最大局部拉伸区域。

## 自检清单

- 原始歌曲未被覆盖，click 资产未被覆盖。
- Python 命令全部通过 uv 执行。
- 音高比例为 `1.0`，未采用改变采样率的伪变速。
- click 使用固定资产，未被时间拉伸；频率等于目标音乐 BPM 的两倍。
- 每个 click 等音量，奇偶位幅度比接近 `1.00`。
- 节拍器全程固定，不存在强拍重音、ducking 或逐段音量调整。
- 自动模式已使用真实拍点检查 P95 和首尾漂移，不能只验证开头。
- 输出按白名单格式编码后重新解码，采样率、时长、最终峰值、延迟和尾部均已验收。
- 报告可解析，`passed` 与具名 acceptance checks 一致。
