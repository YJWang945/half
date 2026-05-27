# HALF 自动结构化 Handoff 实现说明（交付给实现智能体）

## 1. 文档目的

本文档用于指导另一个智能体在 HALF 项目中实现“自动结构化 handoff 草稿生成”能力。目标不是重构整个 handoff 系统，而是在现有 handoff 机制基础上，增加一个**最小侵入式**的自动生成流程，使系统能够根据上游任务上下文，为某条依赖边自动生成 `summary + details` 格式的 handoff 草稿，并支持负责人确认后保存。

---

## 2. 背景与问题

HALF 当前已经支持：

- handoff 作为**边级对象**存在
- DAG finalize 时自动为依赖边创建占位 handoff
- 负责人手工编辑 `summary` 和 `details`
- 使用模板生成 handoff 草稿
- 下游 prompt 显式消费入边 handoff
- handoff 为空时，回退到前序目录 + `result.json`

当前问题是：

- handoff 仍主要依赖人工填写或静态模板
- 上游已有的任务上下文（`result.json`、报告、工件路径等）没有被自动利用
- 复杂任务下，负责人仍需要手工整理交接信息

因此，本次实现的目标是：

> 在现有 `summary + details` schema 不大改动的前提下，为 handoff 增加“根据上游上下文自动生成草稿”的能力。

---

## 3. 本次实现范围

### 3.1 要做的事情

实现一个自动结构化 handoff 草稿生成流程，输入为当前 handoff 对应依赖边的上下文，输出为：

```json
{
  "summary": "...",
  "details": "..."
}
```

并满足：

- `summary` 为高密度交接摘要
- `details` 为固定 Markdown section 的弱结构化内容
- 输出结果作为 **draft** 展示给负责人，由负责人确认后保存

### 3.2 不做的事情

本次不实现以下内容：

- 不重构 handoff 顶层 schema
- 不引入复杂状态机（可后续扩展）
- 不做 handoff revision 历史
- 不做全局 memory / knowledge base
- 不做复杂 workflow / routing 语义
- 不做自动直接发布为 confirmed handoff
- 不做训练新模型

---

## 4. 设计原则

### 4.1 顶层 schema 保持不变

继续沿用现有 handoff 顶层结构：

- `summary`
- `details`

不要引入大量新字段，避免影响现有数据层、API 和前端。

### 4.2 `details` 使用固定 section

`details` 不是自由散文，而应按固定 Markdown 小节组织。建议固定以下 section：

```md
## 核心变更
## 下游必看
## 待继续执行
## 风险提示
## 未决问题
## 相关工件
```

说明：

- 如果某一类内容为空，可以省略该 section
- section 标题尽量固定，后续便于轻量解析和实验分析

### 4.3 自动生成是“草稿”，不是直接生效

自动生成结果默认是 draft，负责人应可查看、修改、确认后保存。

### 4.4 采用混合式生成策略

本次实现不应让 LLM 从全部上下文直接自由生成，而应采用：

> 规则抽取 + LLM 语义选择 + 模板渲染

原因：

- 规则抽取保证确定性（如 task id、工件路径）
- LLM 语义选择负责筛选对下游最有用的信息
- 模板渲染保证输出结构稳定

---

## 5. 整体方法框架

建议按下面的流水线实现：

```text
Source Context Bundle
→ Fact Extraction
→ Handoff Rendering
→ Validation
→ Return Draft
```

其中：

### 5.1 Source Context Bundle
构造与当前 handoff 对应边相关的输入上下文包。

### 5.2 Fact Extraction
先抽取一层中间事实对象，而不是直接生成最终 handoff。

### 5.3 Handoff Rendering
将中间事实对象渲染成最终的 `summary + details`。

### 5.4 Validation
对生成结果做轻量校验，避免空字段或明显错误。

### 5.5 Return Draft
返回给前端展示，默认作为草稿，由负责人决定是否保存。

---

## 6. 输入设计：Source Context Bundle

为某条 handoff 生成草稿时，需要构建输入上下文包。建议至少包含：

### 6.1 边信息

- `from_task_code`
- `to_task_code`
- `edge_type`

#### edge_type 规则建议
可先根据任务类型或模板名称做简单推断，优先支持：

- `dev-to-test`
- `dev-to-review`
- `test-to-revise`
- `review-to-revise`
- `general`

如果当前系统中没有强类型映射，也可以先默认 `general`。

### 6.2 上游任务信息

- 上游任务名称
- 上游任务描述
- 上游任务结果状态
- 上游角色（如 impl/test/review，可选）

### 6.3 下游任务信息

- 下游任务名称
- 下游任务描述
- 下游角色 / 目标（可选）

### 6.4 上游结果信息

优先收集：

- 上游 `result.json`
- 上游报告内容（若有）
- 上游任务目录下的主要工件路径

### 6.5 工件信息

建议至少收集：

- 路径
- 类型
- 简短说明（若已有）

---

## 7. 第一阶段：Fact Extraction

### 7.1 目标

这一阶段不要直接输出 handoff，而是先输出一个中间事实对象。

### 7.2 中间事实对象建议

```json
{
  "core_outcome": "",
  "key_changes": [],
  "required_for_downstream": [],
  "pending_actions": [],
  "risks": [],
  "open_questions": [],
  "artifact_refs": []
}
```

字段语义如下：

- `core_outcome`：上游核心结果
- `key_changes`：关键改动
- `required_for_downstream`：下游必须优先关注的信息
- `pending_actions`：下游继续执行事项
- `risks`：风险 / caveats
- `open_questions`：尚未明确的问题
- `artifact_refs`：需要交给下游查看的工件

### 7.3 各字段生成建议

#### （1）`core_outcome`
来源优先级：

1. `result.json.summary`
2. 上游报告中的结论段
3. 上游任务完成描述

实现方式：

- 先用规则抽出可用文本
- 再由 LLM 重写为简洁结论

#### （2）`key_changes`
来源：

- `result.json`
- 报告中的“核心变更”
- patch / diff 摘要（若容易拿到）

实现方式：

- 先抽出候选文本
- 再由 LLM 选出最值得交接的改动点

#### （3）`required_for_downstream`
来源：

- 下游任务描述
- 当前边类型
- 上游关键变更和风险

实现方式：

- 主要由 LLM 根据“下游要做什么”进行条件化抽取

这是最关键字段。

#### （4）`pending_actions`
来源：

- 报告中的 TODO / follow-up
- 仍未完成但应由下游继续做的事项

实现方式：

- 规则识别 + LLM 标准化

#### （5）`risks`
来源：

- result 中的 caveats / notes
- 报告中的限制条件
- 未覆盖分支、未验证场景等

实现方式：

- 规则抽取候选
- LLM 去重与归纳

#### （6）`open_questions`
来源：

- 报告中的待确认项
- unresolved notes
- 明确的问句或 FIXME 类内容

实现方式：

- 规则识别 + LLM 标准化表述

#### （7）`artifact_refs`
来源：

- 上游输出目录
- `result.json`
- 已登记的工件列表

实现方式：

- **路径必须由规则确定**
- 如需说明文字，可由 LLM 生成简短 description

不要让 LLM 自由编造路径。

---

## 8. 第二阶段：Handoff Rendering

### 8.1 最终输出格式

保持现有 schema：

```json
{
  "summary": "...",
  "details": "..."
}
```

### 8.2 `summary` 设计

要求：

- 1–2 句
- 高密度说明上游做了什么
- 明确下游最应优先关注什么
- 必要时点出最关键风险

### 8.3 `details` 设计

按固定 section 渲染：

```md
## 核心变更
- ...

## 下游必看
- ...

## 待继续执行
- ...

## 风险提示
- ...

## 未决问题
- ...

## 相关工件
- ...
```

### 8.4 实现建议

第一版建议：

- `summary`：由 LLM 基于中间事实对象生成
- `details`：优先通过程序模板渲染
- 不必让 LLM 从零写整段 `details`

也就是说，第一版更推荐：

```text
facts → summary by LLM
facts → details by renderer
```

而不是：

```text
facts → summary/details both fully by LLM
```

这样更稳定，也更容易调试。

---

## 9. 按边类型渲染模板

不同 `edge_type` 的重点 section 可以不同。

### 9.1 `dev-to-test`
重点保留：

- 核心变更
- 下游必看
- 风险提示
- 相关工件

### 9.2 `dev-to-review`
重点保留：

- 核心变更
- 下游必看
- 风险提示
- 相关工件

必要时将“待继续执行”弱化。

### 9.3 `test-to-revise`
重点保留：

- 下游必看
- 待继续执行
- 风险提示
- 相关工件

### 9.4 `general`
默认全部 section 可用，但为空则省略。

---

## 10. Validation（校验）

自动生成结果返回前，建议至少做以下校验：

### 10.1 结构校验
- `summary` 不为空
- `details` 不为空
- 至少包含一个有效 section

### 10.2 内容校验
- 工件路径存在
- 不引用明显不存在的文件
- `from_task_code / to_task_code` 与当前 handoff 匹配

### 10.3 失败处理
如果校验失败：

- 返回带 warning 的 draft
- 不自动覆盖正式 handoff
- 前端提示负责人检查

---

## 11. 推荐 API 设计

### 11.1 新增接口建议

#### `POST /api/handoffs/{handoff_id}/generate-auto-draft`

作用：
- 根据当前 handoff 对应边的上下文自动生成 handoff 草稿
- 不直接覆盖正式 handoff，先返回 draft 内容给前端

建议返回：

```json
{
  "summary": "...",
  "details": "...",
  "warnings": [],
  "source_info": {
    "edge_type": "dev-to-test",
    "used_result_json": true,
    "used_report": true,
    "artifact_count": 2
  }
}
```

### 11.2 是否自动保存
第一版不建议自动保存，建议由前端确认后再调用现有 `PUT /api/handoffs/{handoff_id}` 保存。

---

## 12. 推荐实现位置

可新增一个专门服务，例如：

- `src/backend/services/handoff_auto_generator.py`

建议内部拆分函数：

- `build_source_context_bundle(handoff_id)`
- `extract_handoff_facts(bundle)`
- `render_handoff_from_facts(facts, edge_type)`
- `validate_handoff_draft(draft)`
- `generate_handoff_draft(handoff_id)`

这样结构最清晰，也便于后续测试。

---

## 13. Prompt 设计建议

### 13.1 第一阶段 prompt（Fact Extraction）
提示重点：

- 你不是在写摘要，而是在抽取交接事实
- 目标是帮助下游任务执行
- 不要重复无关背景
- 不要编造工件路径
- 输出必须对齐中间事实对象

### 13.2 第二阶段 prompt（Summary Generation）
提示重点：

- 基于已抽取事实写 summary
- 只写 1–2 句
- 强调下游需要优先关注的点
- 不引入新的事实

### 13.3 不建议
不建议第一版就做“一个 prompt 直接从长上下文生成完整 handoff”。

---

## 14. 前端交互建议

在任务详情页的出边 handoff 区域增加：

- “自动生成草稿”按钮
- 生成后自动填充 `summary` / `details`
- 显示 warnings（如有）
- 负责人可直接编辑后保存

这样不会破坏现有编辑流程。

---

## 15. 测试建议

建议至少覆盖以下测试：

### 15.1 单元测试
- context bundle 构建正确
- 工件路径收集正确
- markdown 渲染正确
- 空字段时 section 省略正确
- 校验逻辑正确

### 15.2 集成测试
- 有 `result.json` + 报告时可生成 draft
- 没有报告时仍可生成 draft
- 没有工件时不报错
- 自动生成后可通过现有 PUT 接口保存

### 15.3 回归测试
- 不影响现有手工编辑
- 不影响模板生成
- 不影响 prompt 消费路径

---

## 16. 验收标准（第一版）

实现完成后，至少满足：

1. 可为指定 handoff 自动生成草稿  
2. 输出仍为现有 `summary + details`  
3. `details` 使用固定 section  
4. 工件路径来自规则抽取，不由 LLM 编造  
5. 草稿可在前端查看和修改  
6. 保存后下游 prompt 能正常消费  
7. 不破坏现有模板生成与手工编辑逻辑  

---

## 17. 备注

本次实现是论文原型与系统能力建设的第一阶段，重点是：

- 跑通自动结构化 handoff 的最小闭环
- 保持现有 schema 稳定
- 让后续实验可以比较：
  - 无 handoff
  - 自由文本 handoff
  - 人工结构化 handoff
  - 自动结构化 handoff

请优先保证：

- 结构清晰
- 结果稳定
- 易于测试

而不是一开始就追求过度复杂或完全自动化。

---

## 18. 一句话总结

请实现一个 **最小侵入式的自动结构化 handoff 草稿生成服务**：

- 从当前 handoff 对应边的上下文中收集信息
- 先抽取中间事实对象
- 再生成 `summary + 固定 section 的 details`
- 返回 draft 给前端
- 由负责人确认后保存
