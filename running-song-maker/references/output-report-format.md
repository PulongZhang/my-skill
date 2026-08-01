# 输出报告格式

脚本在成品旁生成 UTF-8 JSON 报告。报告用于说明实际执行过程和客观测量结果，不代替用户对人声自然度的试听。

## 顶层字段

```json
{
  "input": {},
  "analysis": {},
  "processing": {},
  "click": {},
  "loudness": {},
  "alignment": {},
  "output": {},
  "warnings": [],
  "passed": true
}
```

## input

- `path`：输入文件绝对路径。
- `sample_rate`：解码后的采样率。
- `channels`：声道数。
- `duration_seconds`：原曲时长。

## analysis

- `raw_bpm`：分析器原始 BPM。
- `source_bpm`：处理半速/倍速歧义后的 BPM。
- `beat_count`：检测到的四分音符拍点数。
- `anchor_seconds`：使用的正拍锚点。
- `grid_error_p50_ms`、`grid_error_p95_ms`：原曲拍点相对拟合网格的误差。
- `confidence`：基于拍点数量和网格误差计算的 0～1 置信度。

## processing

- `target_bpm`：目标音乐 BPM。
- `cadence_spm`：目标步频，即目标 BPM 的两倍。
- `stretch_ratio`：目标 BPM 除以原曲 BPM。
- `stretch_percent`：相对原曲的速度变化百分比。
- `engine`：`rubberband`、`ffmpeg-atempo` 或 `none`。
- `tempo_mode`：`global` 或 `strict`。
- `pitch_ratio`：音高比例，当前固定为 `1.0`。
- `centre_focus`：是否启用 Rubber Band 立体声中心聚焦。formant 选项仅在移调时有效，本 Skill 不移调。

## click

- `asset`：click 固定资产路径。
- `count`：实际放置数量。
- `interval_seconds`：相邻 click 间隔。
- `rate_per_minute`：实际每分钟次数。
- `first_seconds`、`last_seconds`：首尾 click 时间。
- `peak_dbfs`：校准后的固定峰值。
- `odd_even_peak_ratio`：奇偶 click 峰值比，预期接近 1.00。
- `rendered_peak_dbfs`：实际渲染 click 轨的峰值。

## loudness

- `music_rms_before_dbfs`：音乐调整前全曲 RMS。
- `music_gain_db`：音乐最终整体增益。
- `music_rms_after_dbfs`：混音前调整后音乐 RMS。
- `click_peak_over_music_rms_db`：click 峰值与音乐 RMS 差。
- `mixed_peak_dbfs`：混音成品峰值。
- `clipped`：是否超过 0 dBFS。
- 压缩输出额外包含 `decoded_peak_dbfs` 和 `estimated_delay_seconds`：重新解码成品后的峰值，以及相对无损母带的估计编码器延迟/填充。

## alignment

- `predicted_p50_ms`、`predicted_p95_ms`：变速映射后拍点相对 click 正拍网格的误差。
- `estimated_end_drift_ms`：末端相对网格的预计漂移。
- `threshold_p95_ms`：验收阈值，默认 30 ms。
- `passed`：是否通过对齐验收。

## output

- `path`：成品绝对路径。
- `report_path`：报告绝对路径。
- `sample_rate`、`channels`、`duration_seconds`：输出属性。
- `format`：输出文件格式。

## warnings 与 passed

`warnings` 应包含：

- 大幅变速；
- 自动检测置信度低；
- 使用 FFmpeg 后备引擎；
- 用户强制全局模式但预计存在漂移；
- 音乐因防止削波被额外降低；
- 压缩格式可能存在编码器延迟。

`passed` 只有在以下条件全部成立时才为 `true`：

- 输出可重新读取；
- 无削波；
- click 频率正确且奇偶等音量；
- 预计 P95 对齐误差不超过阈值；
- 没有未确认的大幅变速或低置信度失败项。
