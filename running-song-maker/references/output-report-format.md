# 输出报告格式

脚本在成品旁生成 UTF-8 JSON 报告。报告说明实际执行过程和客观测量结果，不代替用户对人声自然度的试听。报告生成失败属于处理错误；输出已生成但自动检查失败时，报告仍应保留并将退出码设为 `3`。

## 顶层字段

```json
{
  "input": {},
  "analysis": {},
  "processing": {},
  "click": {},
  "loudness": {},
  "alignment": {},
  "acceptance": {"checks": {}, "passed": false},
  "output": {},
  "warnings": [],
  "passed": false
}
```

顶层 `passed` 必须等于 `acceptance.checks` 所有适用检查的逻辑与；不能因为输出文件存在就设置为 `true`。

## input

- `path`：输入文件绝对路径。
- `sample_rate`：解码后的输入采样率。
- `channels`：输入声道数。
- `duration_seconds`：输入时长。

## analysis

- `raw_bpm`：自相关候选中的原始 BPM。
- `source_bpm`：仅依据音频证据解析后的源 BPM。
- `beat_count`：实际检测到的四分音符拍点数，不包括缺失拍的理论回填。
- `observed_beat_ratio`：实际观测拍点占理论候选网格的比例。
- `max_missing_beat_run`：理论 ordinal 网格中最大连续缺拍数量；长区间会降低置信度并影响 auto 模式。
- `anchor_seconds`：使用的正拍锚点。
- `anchor_is_manual`：是否由 `--first-beat` 提供锚点。
- `grid_error_p50_ms`、`grid_error_p95_ms`：实际拍点相对源网格的误差。
- `estimated_end_drift_ms`：实际观测 residual 的首尾漂移。
- `confidence`：由 hit ratio、观测覆盖率、网格质量和候选 margin 组成的 0～1 置信度。
- `candidate_margin`：最佳源 BPM 候选与次佳候选的归一化差距。

## processing

- `target_bpm`：目标音乐 BPM。
- `cadence_spm`：目标步频，即目标 BPM 的两倍。
- `stretch_ratio`：目标 BPM 除以源 BPM。
- `stretch_percent`：相对源 BPM 的速度变化百分比。
- `engine`：`rubberband`、`ffmpeg-atempo` 或 `none`。
- `tempo_mode`：`global` 或 `strict`。
- `pitch_ratio`：音高比例，当前固定为 `1.0`。
- `actual_bpm`：用于生成 click 的实际拟合四分音符 BPM；应与 `target_bpm` 接近。
- `centre_focus`：是否启用 Rubber Band 立体声中心聚焦。
- `time_map_anchor_stride_beats`：strict time map 的 musical ordinal 锚点间隔；global/none 时为 `null`。
- `local_tempo_ratio_min`、`local_tempo_ratio_max`：strict time map 的局部倍率范围；global/none 时为 `null`。

## click

- `asset`：固定 click 资产路径。
- `count`：实际放置数量；末端不足以完整播放素材的 click 会省略。
- `interval_seconds`：相邻 click 间隔。
- `rate_per_minute`：实际 click 每分钟次数。
- `target_rate_per_minute`：目标 `target_bpm × 2`。
- `first_seconds`、`last_seconds`：首尾 click 时间。
- `peak_dbfs`：校准后的固定 click 峰值。
- `odd_even_peak_ratio`：奇偶 click 峰值比，预期接近 `1.00`。
- `rendered_peak_dbfs`：实际渲染 click 轨的峰值。

## loudness

- `music_rms_before_dbfs`：音乐调整前全曲 RMS。
- `music_gain_db`：音乐最终整体增益，只允许为非正值。
- `music_rms_after_dbfs`：混音前调整后音乐 RMS。
- `click_peak_over_music_rms_db`：click 峰值与音乐 RMS 差。
- `mixed_peak_dbfs`：PCM 混音母带峰值。
- `decoded_peak_dbfs`：最终输出重新解码后的峰值。
- `peak_ceiling_passed`：解码峰值是否不超过用户配置的 ceiling（含明确小容差）。
- `mixed_peak_dbfs`、`decoded_peak_dbfs` 均应同时结合 `clipped` 阅读。
- `clipped`：是否超过 `0 dBFS`。
- `estimated_delay_seconds`：有损输出相对 PCM 母带的估计起始延迟；无损输出为 `0`。
- `tail_padding_samples`：相对 PCM 母带和估计 delay 的尾部帧差。
- `duration_error_seconds`：解码输出时长减去 PCM 母带时长。
- `duration_passed`：时长是否在对应格式容差内。
- `extra_headroom_reduction_db`：为保持 click 固定且避免削波而额外降低音乐的幅度（若报告实现提供该字段）。

## alignment

- `predicted_p50_ms`、`predicted_p95_ms`：变速映射后实际 beat observation 相对 click 网格的误差。
- `estimated_end_drift_ms`：首尾 residual 漂移。
- `threshold_p95_ms`：最终 alignment 检查阈值，默认 `30 ms`。
- `threshold_end_drift_ms`：最终首尾漂移阈值，默认 `50 ms`。
- `passed`：P95 和首尾漂移是否都通过最终阈值。

`auto` 选择 strict 使用更保守的决策阈值：P95 `25 ms` 或首尾漂移 `50 ms` 任一超限即切换 strict；用户强制 global 时仍要保留预测数值和 warning。

## acceptance

`acceptance.checks` 使用具名布尔字段：

```json
{
  "output_readable": true,
  "sample_rate": true,
  "channels": true,
  "duration": true,
  "final_peak_ceiling": true,
  "not_clipped": true,
  "codec_delay": true,
  "click_cadence": true,
  "click_equal_volume": true,
  "alignment_p95": true,
  "alignment_end_drift": true
}
```

- `output_readable`：最终文件可重新解码。
- `sample_rate`、`channels`：符合输出格式计划和处理前声道数。
- `duration`：输出时长在无损/有损对应容差内。
- `final_peak_ceiling`：重新解码峰值不超过用户 ceiling。
- `not_clipped`：重新解码峰值不超过 `0 dBFS`。
- `codec_delay`：有损编码延迟在报告容差内；无损格式适用时直接通过。
- `click_cadence`：实际 click 频率与目标 cadence 的差值在容差内。
- `click_equal_volume`：奇偶 click 峰值比至少为 `0.99`。
- `alignment_p95`、`alignment_end_drift`：最终对齐误差检查。

`acceptance.passed` 与顶层 `passed` 相同。

## output

- `path`：成品绝对路径。
- `report_path`：报告绝对路径。
- `sample_rate`、`channels`、`duration_seconds`：最终重新解码输出属性。
- `expected_duration_seconds`：PCM 混音母带时长。
- `duration_error_seconds`：最终输出与母带的时长差。
- `format`：输出扩展名对应的白名单格式；MP3/Opus 计划为 `48 kHz`，AAC 的 priming 使用 codec-aware 容差。

## warnings 与退出码

`warnings` 可能包含：

- 大幅变速或低置信度被用户显式接受；
- 使用 FFmpeg global 后备引擎；
- 用户强制 global 但预测存在漂移；
- 音乐因防止削波被额外降低；
- 压缩格式存在编码器延迟或尾部 padding；
- 最终某项自动验收失败。

- 退出码 `0`：输出和所有适用 acceptance checks 通过。
- 退出码 `3`：输出已生成，但自动验收失败。
- 退出码 `2`：参数、依赖、输入、路径或处理错误，未完成有效成品。
