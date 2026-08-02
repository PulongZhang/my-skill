# 音频处理规范

## 1. 时间与步频定义

本 Skill 将歌曲 BPM 视为四分音符速度，将跑步步频视为每半拍一次落脚：

```text
cadence = target_bpm * 2
click_interval_seconds = 60 / cadence = 30 / target_bpm
```

| 音乐 BPM | 跑步步频 | click 间隔 |
| ---: | ---: | ---: |
| 90 | 180 次/分钟 | 333.333 ms |
| 95 | 190 次/分钟 | 315.789 ms |

每个 click 的采样位置必须从统一锚点直接计算：

```text
sample[n] = round((anchor_time + n * 30 / target_bpm) * sample_rate)
```

不要累计浮点间隔，因为长歌曲中会积累舍入漂移。末端不足以完整播放 click 素材时省略该末端 click，不把截断 click 伪装成等音量 click。

## 2. 源 BPM 与目标 BPM

源 BPM 只由音频证据决定，不把 90/95 目标偏好放入源 BPM 候选评分。分析器从 onset 包络的自相关候选生成半速/倍速变体，在 `70～130 BPM` 范围内用网格能量、按拍点数归一化的 hit ratio 和自相关 prominence 解析源 BPM，并保留候选 margin。

目标自动选择只在源 BPM 已确定后比较 90 和 95 BPM，并按相对变速比例最小选择：

```text
stretch_ratio = target_bpm / source_bpm
stretch_percent = (stretch_ratio - 1) * 100
```

`--max-stretch-percent` 只能降低默认阈值，不能高于 `12%`；超过有效阈值必须显式使用 `--allow-large-stretch`。

## 3. 拍点观测和锚点

使用打击乐成分的 onset strength 跟踪四分音符拍点。理论网格仅用于提出候选位置；只有窗口内找到合格 onset 才记录为实际 beat observation。缺拍不回填理论时间，并保留原始 musical ordinal 跳号，以免把缺拍误判成真实恒速证据。

若用户提供 `first_beat`：

- 把它作为权威正拍 ordinal `0`；
- 自动检测仍用于估计 BPM 和局部漂移；
- global 输出 click 相位锁定为 `first_beat / stretch_ratio`；
- strict time map 删除可能重复的自动 ordinal-0 landmark；
- click 网格从该锚点向前、向后推算到完整输出范围。

分析报告同时记录观测覆盖率、P50、P95、首尾 residual drift、置信度和是否使用手工 anchor。

## 4. Global 模式与 auto 决策

global 变速使用：

```text
output_time = input_time / stretch_ratio
```

原曲真实拍点映射为：

```text
output_beat[i] = input_beat[i] / stretch_ratio
```

目标 BPM 选定后，先用这些真实观测预测 global 的 P50、P95 和首尾漂移。`auto` 在以下任一条件成立时选择 strict：

```text
predicted_p95_ms > 25 ms
or estimated_end_drift_ms > 50 ms
```

用户强制 `--tempo-mode global` 时仍可生成，但报告必须保留非零预计误差并给出 warning。global 变速后的 click 周期只在目标 BPM 附近进行受约束拟合，不能重新自由分析成半速或倍速 alias。实际 click cadence 还要单独与 `target_bpm × 2` 比较。

## 5. Strict 时间映射

局部速度漂移明显时使用 Rubber Band CLI time map：

- 输入、输出均使用同一采样率的浮点 PCM WAV；
- strict 没有独立 Rubber Band CLI 时明确失败，FFmpeg `atempo` 不能替代；
- 输入 beat ordinal 显式传入，stride 按 musical ordinal 选择，而不是按观测数组位置选择；
- 手工 anchor 作为 ordinal 0 的唯一权威 landmark；
- 默认优先每 4 拍设置锚点，必要时尝试更密的 2 拍或 1 拍锚点；
- source frame、target frame 均严格递增，不写入 `0 0`；
- 保留尾部并按全局倍率外推；
- 检查局部倍率安全范围和 time-map 预测 P95；超出时停止，不强行破坏人声。

不要把每拍切成独立音频块再拼接。时间映射必须由同一次离线处理连续完成。

## 6. 人声保护

正式成品优先使用 Rubber Band R3/Finer 高质量离线引擎。音高比例固定为 `1.0`，不使用 `--pitch` 或 `--frequency`。`--formant` 只在移调时保护共振峰，本 Skill 不移调，因此无需启用。立体声中心人声默认使用 `--centre-focus`；如果用户更重视声场宽度，可关闭后对比试听。

质量风险按绝对变速百分比提示：

- ≤5%：低风险；
- 5%～8%：一般风险；
- 8%～12%：较高风险，需要重点试听；
- >12%：默认拒绝，除非用户明确允许。

FFmpeg `atempo` 只能用于 global 变速后备方案。存在明显局部漂移时，不得用 FFmpeg 输出并宣称严格对齐。

## 7. 固定 click

固定资产：

```text
assets/running_wood_click_580hz_soft6ms.wav
```

参考特征：

- 木质、非谐波 click；
- 描述频率约 580 Hz；
- 约 6 ms 软攻击；
- 频谱质心约 655 Hz；
- 单声道素材，混音时复制到所有输出声道；
- 不做时间拉伸，不做奇偶增益，不做强拍重音。

允许对采样率进行高质量重采样，并统一调整一次固定峰值；除此之外不要改变其包络或频谱。

## 8. 响度和混音

默认：

```text
click_peak_dbfs = -6
click_over_music_rms_db = 16
music_rms_target_dbfs = -22
output_peak_ceiling_dbfs = -1
```

音乐增益遵循：

```text
music_gain_db = min(0, click_peak_dbfs - 16 - measured_music_rms_dbfs)
```

混合后若超过输出峰值上限，继续降低音乐，click 仍保持固定。不要用 limiter、压缩器、ducking 或整体归一化掩盖削波。

## 9. 编解码与输出格式

推荐流程：

```text
解码一次 → 浮点 PCM 分析与处理 → 混音 → 写入/编码 → 重新解码验收
```

输出扩展名白名单为 `.wav`、`.flac`、`.mp3`、`.m4a`、`.aac` 和 `.opus`；未知扩展名在处理前失败。WAV/FLAC 使用 PCM24；MP3/M4A/AAC 使用明确 FFmpeg 编码参数；MP3 和 Opus 明确以 `48 kHz` 编码，其他格式沿用处理采样率。AAC 原始流保留为可选输出，但按其正常 encoder priming 使用更宽的 codec-aware duration/delay 容差，并将测量结果写入报告。

有损编码可能加入延迟或尾部 padding。重新解码后必须核对计划采样率、声道、内容时长、最终峰值、估计 codec delay 和 tail padding；不能只检查文件存在。容差按 codec 选择，不能用一个低于 AAC frame duration 的固定阈值拒绝所有正常 AAC 文件。

## 10. 失败和退出条件

遇到以下情况应返回明确错误或验收失败：

- 拍点数量不足或真实观测覆盖不足；
- BPM 置信度低且用户未确认；
- 自动目标需要超过 12% 变速且用户未允许；
- 严格模式缺少 Rubber Band CLI；
- FFmpeg 不存在但输入或输出格式需要编解码；
- 输入、输出、报告或 click 路径碰撞；
- 输出扩展名不在白名单；
- 时间映射不单调；
- 局部时间拉伸比例超出安全范围；
- click 资产不存在或无法读取；
- 混音后即使音乐降低仍发生削波；
- 重新解码后的输出峰值超过用户 ceiling、cadence 偏离目标或 alignment P95/end drift 超阈值；
- 输出文件无法重新读取或报告无法生成。

参数、依赖和处理错误使用退出码 `2`；输出已生成但自动验收失败使用退出码 `3`。
