---
name: jev-api
description: Use when explaining or implementing a call to TypeSafe AI Jev (System One), especially its HTTP request parameters, choice/noul/score questions, and response fields. Do not use for unrelated LLM APIs.
---

# 调用 Jev

Jev 的原生接口把一份待判断的数据 `state` 和一组问题 `questions` 送给指定的 `model`，返回与问题 ID 对应的结构化答案。接入前以 [官方 API 文档](https://docs.typesafe.ai/api/) 和 [模型列表](https://docs.typesafe.ai/models/) 核对接口与可用模型；不要把版本、限额等易变信息当作固定值。

## 发起请求

`POST https://api.typesafe.ai/v1/systemone`，请求头为 `Authorization: Bearer <API_KEY>` 和 `Content-Type: application/json`。从环境变量读取密钥，不要把密钥写进源码。

请求体只有三个顶层字段，均必填：

| 字段 | 类型 | 作用 |
| --- | --- | --- |
| `model` | string | 选择模型。`jev-latest` 指向最新稳定版；需要固定决策表现时可使用经验证的版本 ID。 |
| `state` | string、object 或 array | 提供要评估的文本或结构化业务状态，例如用户消息、工单或聊天记录。 |
| `questions` | object | 以自定义问题 ID 为键，定义一次请求要回答的一个或多个问题；答案沿用相同 ID。 |

每个 `questions.<问题 ID>` 都需要 `type` 和 `instructions`。`type` 决定答案形状；`instructions`（string、object 或 array）说明具体判断目标。不同类型的 `criteria` 用法如下：

| `type` | `criteria` | 用途与结果 |
| --- | --- | --- |
| `choice` | **必填**；选项 ID 到判断标准的映射。标准可为 string、object、array 或 `null`；最多 255 个选项。 | 从候选项中选择；返回 `choice`、每项的 `probabilities` 和 `confidence`。 |
| `noul` | **可选**；对象中的 `true`、`false` 可解释命题成立和不成立的含义。 | 回答是非问题；返回 0～1 的 `noul`，表示“是”的概率。 |
| `score` | **必填**；按从低到高排列的等级数组，建议至少 2 级，最多 10 级。 | 按等级评分；返回概率加权的 `score`，可以是小数，并附 `legend`、`probabilities`、`confidence`。等级下标从 0 开始。 |

最小调用示例（Bash）：

```bash
curl https://api.typesafe.ai/v1/systemone \
  -H "Authorization: Bearer $TYPESAFE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "jev-latest",
    "state": {"message": "商品损坏了，我想退款"},
    "questions": {
      "department": {
        "type": "choice",
        "instructions": "应由哪个部门处理？",
        "criteria": {"billing": "支付和退款", "technical": "技术问题", "other": "其他"}
      },
      "refund_requested": {
        "type": "noul",
        "instructions": "用户是否明确要求退款？"
      },
      "urgency": {
        "type": "score",
        "instructions": "请求有多紧急？",
        "criteria": ["普通", "需要尽快处理", "紧急"]
      }
    }
  }'
```

响应的 `model` 是实际执行的版本，`answers.<问题 ID>` 是对应结果，`usage.input_tokens` 和 `usage.output_tokens` 是用量。`choice` 的 `confidence` 是从概率分布推导的确定性指标，不必等于最高选项的概率；`score` 是各等级下标按概率加权的值。业务阈值应由调用方制定并用自己的数据检验。

原生接口不使用聊天模型常见的 `messages`、`temperature`、`top_p`、`max_tokens` 或 `stream` 字段。请求校验失败先检查字段；遇到 `429` 或 `529` 时按官方建议退避重试。需要查看当前可用模型时，调用带同样 Bearer 鉴权的 `GET https://api.typesafe.ai/v1/models`。
