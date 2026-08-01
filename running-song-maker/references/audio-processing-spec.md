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

不要累计浮点间隔，因为长歌曲中会积累舍入漂移。

## 2. BPM 标准化

分析 BPM 后，将常见半速/倍速结果归一到适合四分音符计拍的范围。默认范围为 `70～130 BPM`：

- 小于 70 时不断乘 2；
- 大于 130 时不断除 2；
- 用归一后的 BPM 重新跟踪四分音符拍点。

目标自动选择只比较 90 和 95 BPM，并按相对变速比例最小选择：

```text
stretch_ratio = target_bpm / source_bpm
```

## 3. 拍点和锚点

使用打击乐成分的 onset strength 跟踪四分音符拍点。以连续拍点拟合网格，不把第一个瞬态直接当作第一拍。

若用户提供 `first_beat`：

- 把它作为可靠正拍锚点；
- 自动检测仍用于估计 BPM 和局部漂移；
- click 网格从该锚点向前、向后推算到完整输出范围。

节拍器不强调小节第一拍，因此不需要强制识别拍号和 downbeat；但锚点必须落在四分音符正拍上，之后在正拍和反拍各放一个等音量 click。

## 4. 全局变速模式

节奏稳定时使用单次全局时间拉伸：

```text
output_time = input_time / stretch_ratio
```

原拍点映射为：

```text
output_beat[i] = input_beat[i] / stretch_ratio
```

对映射后的拍点拟合目标网格，计算残差。默认把 P95 残差不超过 25 ms 视为可接受的恒定速度候选。

## 5. 严格网格模式

局部速度漂移明显时，使用 Rubber Band time map：

- 输入、输出均使用同一采样率的 PCM WAV；
- 当前 Rubber Band R3 time map 不写入 `0 0`，避免其初始比率出现无效值；首个锚点必须是有意义的非零 sample frame；
- 将选定拍点映射到严格目标 BPM 网格；
- 默认每 4 拍设置一个锚点，避免逐拍突变；
- 保留尾部并按全局倍率外推；
- 时间映射必须严格单调；
- 若局部倍率超出安全范围则停止，不强行破坏人声。

不要把每拍切成独立音频块再拼接。时间映射必须由同一次离线处理连续完成。

## 6. 人声保护

正式成品优先使用 Rubber Band R3/Finer 高质量离线引擎。音高比例固定为 `1.0`，不使用 `--pitch` 或 `--frequency`。`--formant` 只在移调时保护共振峰，本 Skill 不移调，因此无需启用。立体声中心人声默认使用 `--centre-focus`；如果用户更重视声场宽度，可关闭后对比试听。

质量风险按绝对变速百分比提示：

```text
abs(stretch_ratio - 1) * 100
```

- ≤5%：低风险；
- 5%～8%：一般风险；
- 8%～12%：较高风险，需要重点试听；
- >12%：默认拒绝，除非用户明确允许。

FFmpeg `atempo` 只能用于全局变速后备方案。存在明显局部漂移时，不得用 FFmpeg 输出并宣称严格对齐。

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
music_rms_ceiling_dbfs = -22
output_peak_ceiling_dbfs = -1
```

音乐增益：

```text
music_gain_db = min(0, click_peak_dbfs - 16 - measured_music_rms_dbfs)
```

混合后若超过输出峰值上限，继续降低音乐，click 仍保持固定。不要用 limiter、压缩器、ducking 或整体归一化掩盖削波。

## 9. 编解码顺序

推荐流程：

```text
解码一次 → 浮点 PCM 分析与处理 → 混音 → 验证 → 编码一次
```

MP3/AAC 编码器可能加入延迟。节拍定位和混音必须在 PCM 时间轴完成；若输出压缩格式，应重新解码成品并核对时长和起始延迟。

## 10. 失败条件

遇到以下情况应返回明确错误或警告：

- 拍点数量不足；
- BPM 置信度低；
- 自动目标需要超过 12% 变速且用户未允许；
- 严格模式缺少 Rubber Band；
- FFmpeg 不存在但输入或输出格式需要编解码；
- 时间映射不单调；
- 局部时间拉伸比例超出安全范围；
- click 资产不存在或无法读取；
- 混音后即使音乐大幅降低仍发生削波；
- 输出文件无法重新读取或报告无法生成。
