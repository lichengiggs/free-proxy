# free-proxy 开发蓝图

## 1. 需求源确认

- 唯一需求文档：`spec.md`
- 本文所有方案、拆解、验收映射均以 `spec.md` 为准
- 当前仓库未发现其他 `prd.md` 或历史 `plan.md`，不存在需求源冲突

## 2. 问题定义

当前 `free-proxy` 的主要失败点不是“免费模型没有被遍历到”，而是：

1. 请求进入上游前没有做预算控制，导致 OpenClaw 这类长上下文请求把免费模型直接压垮。
2. fallback 仍偏静态，遇到连续失败时会重复命中近期不健康模型，造成长链路无效重试。
3. 日志粒度不够，难以快速区分是上下文过大、模型额度不足、provider 故障还是请求体不兼容。

本次开发的核心就是把代理层从“静态转发器”升级为“会降载、会避障、会解释自己决策”的路由层。

## 3. 总体设计

## 3.1 模块改造概览

### 现有模块

- `src/server.ts`：请求入口与上游转发
- `src/fallback.ts`：回退链构建与执行
- `src/rate-limit.ts`：限流状态持久化
- `src/models.ts`：模型发现与基础属性
- `src/provider-health.ts`：provider / model 可用性探测

### 新增模块建议

- `src/request-budget.ts`
  - 负责 token 估算、风险等级判断、预算阈值读取
- `src/context-optimizer.ts`
  - 负责简单消息裁剪（保留 system + 最新 user + 可选最后 assistant）
- `src/model-health.ts`
  - 负责模型级 / provider 级失败统计、熔断状态、动态降权计算
- `src/logger.ts` 或轻量日志辅助函数
  - 负责结构化打印预算动作、排序原因、跳过原因

### 尽量复用的模块

- `src/rate-limit.ts`
  - 继续保存 rate limit 冷却状态
  - 可扩展为统一持久化失败冷却/熔断状态，避免重复存储

## 3.2 核心数据流

### 新请求路径

1. `POST /v1/chat/completions` 进入 `src/server.ts`
2. 解析请求体后，调用 `request-budget.ts` 估算 token
3. 若超阈值，调用 `context-optimizer.ts` 做简单裁剪
4. 生成最终上游 payload
5. 调用 `fallback.ts` 执行 fallback，但在排序前接入 `model-health.ts` 的动态评分与熔断状态
6. 每次失败写入模型健康状态；每次成功恢复部分权重/关闭熔断
7. 返回响应，同时在日志中写出预算动作与路由决策

### 失败反馈闭环

1. 上游调用失败
2. 统一错误分类
3. 更新模型失败统计 + provider 失败统计
4. 如果失败信息里明确暴露了上下文上限、TPM 限额或 “request too large” 提示，则把该值记录为观测到的模型 / provider 限额，作为后续预算修正依据
5. 对“请求过大”这一类失败，允许在同一次请求链内先执行一次更保守的裁剪后立即重试，不把它直接当作普通失败继续走长链 fallback
6. 触发模型级或 provider 级熔断/降权
7. 下一次排序立即生效

## 4. 架构与接口设计

## 4.1 请求预算模块 `src/request-budget.ts`

### 职责

- 统一估算输入 token
- 计算请求风险等级
- 读取全局/按 provider/按 model 的预算阈值
- 如果上游失败反馈已经明确给出更低的可用上限，则优先用“观测上限减安全余量”修正预算阈值

### 建议接口

```ts
export type BudgetResult = {
  estimatedInputTokens: number;
  budgetInputLimit: number;
  shouldTrim: boolean;
};

export function evaluateRequestBudget(input: {
  model: string;
  messages: ChatMessage[];
  tools?: unknown[];
}): BudgetResult;
```

### 设计说明

- 第一版不追求 tokenizer 精确度，采用统一估算公式即可
- 工具 schema 和 tool output 单独加权，避免只按 message 文本估算
- 阈值来源：第一期只用全局默认值；后续可加 `model override > provider override > global default`
- 当失败反馈明确给出更低的上限时，后续预算阈值应在该上限基础上再保留一档安全余量，避免再次贴边

## 4.2 上下文优化模块 `src/context-optimizer.ts`

### 职责

- 简单截断：保留关键消息，删除中间历史

### 建议接口

```ts
export type OptimizeContextInput = {
  messages: ChatMessage[];
  budget: BudgetResult;
};

export type OptimizeContextResult = {
  messages: ChatMessage[];
  trimmed: boolean;
  beforeTokens: number;
  afterTokens: number;
};

export function optimizeRequestContext(input: OptimizeContextInput): OptimizeContextResult;
```

### 行为顺序

1. 保留第一条 system message（如有）
2. 保留最后一轮 user message
3. 可选保留最后一个 assistant 回复（如有）
4. 删除其余所有中间消息
5. 如果裁剪后仍为空，保留原始 messages 不变

## 4.3 模型健康模块 `src/model-health.ts`

### 职责

- 维护模型短期健康度
- 提供熔断状态机
- 计算动态降权分数

### 建议接口

```ts
export type FailureKind =
  | 'rate_limit'
  | 'auth_error'
  | 'provider_unavailable'
  | 'timeout'
  | 'network_error'
  | 'bad_request'
  | 'unknown_error';

export type CircuitState = 'closed' | 'open' | 'half_open';

export function recordModelSuccess(modelId: string, latencyMs: number): Promise<void>;
export function recordModelFailure(modelId: string, provider: string, kind: FailureKind): Promise<void>;
export function getModelCircuitState(modelId: string): CircuitState;
export function getProviderCircuitState(provider: string): CircuitState;
export function getDynamicPenalty(input: {
  modelId: string;
  provider: string;
  risk: RequestRisk;
}): number;
```

### 状态流转

- `closed`：正常
- `open`：连续失败达到阈值后开启，直接跳过
- `half_open`：冷却后允许少量试探
- 成功恢复：`half_open -> closed`
- 再次失败：`half_open -> open`

## 4.4 fallback 改造 `src/fallback.ts`

### 改造点

1. `getFallbackChain()` 之前或内部引入请求风险等级
2. 在排序阶段叠加 `dynamicPenalty`
3. 遇到模型/Provider 熔断状态直接跳过
4. 引入 `FALLBACK_MAX_ATTEMPTS`
5. 返回更多调试信息到日志层

### 新排序公式

```ts
final_score = static_score - dynamic_penalty - circuit_penalty - request_risk_penalty
```

其中：

- `static_score`：保留现有能力/稳定性/上下文等静态评分
- `dynamic_penalty`：最近失败率、连续失败次数、平均耗时
- `circuit_penalty`：熔断状态带来的硬跳过或极大惩罚
- `request_risk_penalty`：大请求场景下对低上下文、小模型、慢模型的额外惩罚

## 4.5 错误分类接入点

### 建议放置位置

- 在 `src/server.ts` 实际请求上游失败的捕获点
- 在 `executeWithFallback()` 中统一转为 `FailureKind`

### 分类规则

- HTTP 429 + 明确额度字样 -> `rate_limit`
- 401 / 403 -> `auth_error`
- 503 -> `provider_unavailable`
- AbortError / timeout -> `timeout`
- fetch 网络异常 -> `network_error`
- 400 / schema 不兼容 -> `bad_request`
- 其余 -> `unknown_error`

## 5. 核心伪代码

## 5.1 请求入口伪代码

```ts
const budget = evaluateRequestBudget({ model, messages, tools, maxTokens });

let optimizedMessages = messages;
let optimizeMeta = null;

if (budget.shouldTrim) {
  optimizeMeta = await optimizeRequestContext({
    model,
    messages,
    tools,
    budget,
  });
  optimizedMessages = optimizeMeta.messages;
}

logRequestBudget({ model, budget, optimizeMeta });

const result = await executeWithFallback(model, async (candidateModel) => {
  const response = await sendUpstream(candidateModel, {
    ...payload,
    messages: optimizedMessages,
  });

  return normalizeExecutionResult(response);
});
```

## 5.2 裁剪伪代码

```ts
function optimizeRequestContext(input) {
  const messages = input.messages;
  if (messages.length <= 2) {
    return { messages, trimmed: false, beforeTokens: input.budget.estimatedInputTokens, afterTokens: input.budget.estimatedInputTokens };
  }

  const systemMsg = messages.find(m => m.role === 'system');
  const lastUserMsg = [...messages].reverse().find(m => m.role === 'user');
  const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant');

  const result = [];
  if (systemMsg) result.push(systemMsg);
  if (lastAssistant && lastAssistant !== systemMsg) result.push(lastAssistant);
  if (lastUserMsg && lastUserMsg !== systemMsg) result.push(lastUserMsg);

  // Safety: if result is empty, return original
  if (result.length === 0) {
    return { messages, trimmed: false, beforeTokens: input.budget.estimatedInputTokens, afterTokens: input.budget.estimatedInputTokens };
  }

  return {
    messages: result,
    trimmed: true,
    beforeTokens: input.budget.estimatedInputTokens,
    afterTokens: estimateTokens(result),
  };
}
```

## 5.3 熔断与动态降权伪代码

```ts
function rankCandidates(models, risk) {
  return models
    .map(model => {
      const staticScore = scoreModel(model);
      const dynamicPenalty = getDynamicPenalty({
        modelId: model.id,
        provider: model.provider,
        risk,
      });
      const circuitState = getModelCircuitState(model.id);

      if (circuitState === 'open') {
        return { model, skipped: true, reason: 'circuit_open' };
      }

      return {
        model,
        skipped: false,
        finalScore: staticScore - dynamicPenalty,
      };
    })
    .filter(item => !item.skipped)
    .sort((a, b) => b.finalScore - a.finalScore);
}

async function onFailure(model, provider, error) {
  const kind = classifyFailure(error);
  await recordModelFailure(model, provider, kind);
}
```

## 6. 具体文件改动清单

## 6.1 新增文件

- `src/request-budget.ts`
  - 预算估算、风险等级、阈值读取
- `src/context-optimizer.ts`
  - 简单消息裁剪（保留 system + 最新 user + 可选最后 assistant）
- `src/model-health.ts`
  - 模型/Provider 健康状态、熔断、动态降权

## 6.2 修改文件

- `src/server.ts`
  - 在上游请求前接入预算评估与上下文优化
  - 补充结构化日志
  - 在错误出口增加失败分类信息
- `src/fallback.ts`
  - 接入请求风险等级
  - 接入模型健康状态
  - 加入最大尝试数、跳过逻辑、动态分数排序
- `src/rate-limit.ts`
  - 评估是否扩展为统一短期状态存储
  - 若不扩展，则保持 rate limit 专职，新增 `model-health-state.json`
- `src/models.ts`
  - 如需，补充供动态评分读取的上下文能力字段回退逻辑
- `src/provider-health.ts`
  - 与失败分类枚举保持一致，避免重复定义错误语义
- `src/config.ts`
  - 读取新增预算/熔断配置项

## 6.3 测试文件

- `__tests__/request-budget.test.ts`
- `__tests__/context-optimizer.test.ts`
- `__tests__/model-health.test.ts`
- `__tests__/fallback.dynamic-ranking.test.ts`
- 视现有结构补充 `__tests__/api-routes.test.ts` 中的集成断言

## 7. 边界情况与异常处理

## 7.1 请求预算相关

- **消息为空**：直接走原始请求；日志标记 `message_count=0`
- **只有一条用户消息**：禁止错误裁剪成空请求
- **system message 超大**：保留 system 不做截断（第一期不做超长 system 处理）
- **tool schema 极大**：只估算，不直接删 schema

## 7.2 fallback 相关

- **全部模型熔断**：允许最后尝试一个兜底模型，随后明确返回“当前所有候选都在冷却中”
- **provider key 失效**：直接强熔断该 provider，并提示检查 key
- **同 provider 不同模型连续 503**：触发 provider 级降级
- **最大尝试数过小导致误伤**：默认值要保守，避免第一次就把成功模型挡掉

## 7.3 状态持久化相关

- **状态文件损坏**：自动回退为空状态并记录错误日志，不能阻塞主请求
- **并发写入**：沿用现有文件锁/原子写策略
- **重启后状态恢复**：仅恢复短期窗口内有效状态，过期状态自动忽略

## 8. 验证方案

## 8.1 单元测试

运行：

```bash
npm test
```

重点检查：

- 超长消息是否触发 `shouldTrim`
- 裁剪后是否保留 system message 和最后一轮用户消息
- 裁剪后消息列表不为空
- 连续失败是否进入 `open -> half_open -> closed` 状态流转
- 动态降权后排序是否变化

## 8.2 类型检查

运行：

```bash
npx tsc --noEmit
```

重点检查：

- 新模块类型是否与现有 `Model` / 路由输入兼容
- 错误分类枚举是否全链路可达

## 8.3 手工联调

启动：

```bash
npm run dev
python3 test_proxy.py --count 2
```

建议追加的验证动作：

1. 构造超长 messages，确认 `output.log` 中出现预算与裁剪日志
2. 故意让某 provider 返回 429，确认后续请求会跳过或降权
3. 连续运行几次，确认 fallback 不再每次都从同一批坏模型开始
4. 查看失败日志，确认可以区分 `rate_limit`、`timeout`、`auth_error`

## 8.4 验收映射

- `spec.md` 验收 1：通过预算日志 + 裁剪测试覆盖
- `spec.md` 验收 2：通过熔断状态流转测试覆盖
- `spec.md` 验收 3：通过动态排序日志 + fallback 排序测试覆盖
- `spec.md` 验收 4：通过结构化错误日志和手工联调覆盖

## 9. 实施顺序

### 第一阶段：预算与裁剪落地

先做 `request-budget.ts` 与 `context-optimizer.ts`，确保请求进入上游前已经“瘦身”。

### 第二阶段：失败分类与健康状态

引入统一失败分类，再实现模型级熔断与动态降权。

### 第三阶段：fallback 重排

把实时健康度接入 `fallback.ts`，限制最大尝试数，输出可解释日志。

### 第四阶段：补测试与日志验证

通过单测、类型检查、联调日志把验收链条闭合。

## 10. PM Review Note

这套方案覆盖 `spec.md` 的方式很直接：

1. `spec.md` 要求“长请求不能再原样硬发”，这里用“预算评估 -> 简单裁剪”兜住。
2. `spec.md` 要求“失败模型不能一直反复撞”，这里用“失败分类 -> 模型熔断 -> provider 降级 -> 动态降权”兜住。
3. `spec.md` 要求“日志要解释清楚为什么失败”，这里把预算动作、排序结果、跳过原因、失败分类都纳入日志。
4. `spec.md` 要求“能验证”，这里已经把单测、类型检查、联调命令和验收映射全部写死，不会出现做了功能却没法证明的情况。

用大白话说：这份计划不是只想着“再多试几个免费模型”，而是先把请求减肥，再让系统学会避开坏路。这样才能真正提升 OpenClaw 这种大请求场景的成功率，也能把 `spec.md` 里写的每条验收标准落到可开发、可测试、可排查的动作上。

## 11. Atomic Todo List

- [ ] 环境/配置准备：确认 `spec.md` 中新增配置项命名，补齐 `src/config.ts` 的读取入口
- [ ] 环境/配置准备：确定健康状态持久化方案，决定复用 `rate-limit-state.json` 还是新增独立状态文件
- [ ] 核心逻辑开发：新增 `src/request-budget.ts`，实现统一 token 估算与预算判断
- [ ] 核心逻辑开发：新增预算阈值读取逻辑，支持全局默认值（后续可扩展 per-model 覆盖）
- [ ] 核心逻辑开发：新增 `src/context-optimizer.ts`，实现简单消息裁剪（保留 system + 最新 user + 可选最后 assistant）
- [ ] 核心逻辑开发：在 `src/server.ts` 中接入预算评估与上下文优化流程
- [ ] 核心逻辑开发：定义统一 `FailureKind`，在上游请求失败处完成错误分类
- [ ] 核心逻辑开发：新增 `src/model-health.ts`，实现模型级失败计数、成功恢复与熔断状态机
- [ ] 核心逻辑开发：在 `src/model-health.ts` 中实现 provider 级失败统计与降级逻辑
- [ ] 核心逻辑开发：在 `src/fallback.ts` 中接入动态降权计算与熔断跳过逻辑
- [ ] 核心逻辑开发：在 `src/fallback.ts` 中加入 `FALLBACK_MAX_ATTEMPTS` 限制
- [ ] 接口/UI 适配：在 `src/server.ts` 中补充预算动作、跳过原因、最终排序分数的结构化日志
- [ ] 接口/UI 适配：如有必要，为管理接口预留只读调试输出结构，但本期不做前端展示
- [ ] 测试验证：新增 `__tests__/request-budget.test.ts` 覆盖预算判断与阈值覆盖
- [ ] 测试验证：新增 `__tests__/context-optimizer.test.ts` 覆盖简单裁剪行为
- [ ] 测试验证：新增 `__tests__/model-health.test.ts` 覆盖熔断状态流转与 provider 降级
- [ ] 测试验证：新增 `__tests__/fallback.dynamic-ranking.test.ts` 覆盖动态降权排序与最大尝试数
- [ ] 测试验证：更新集成测试，验证错误分类、日志关键字段与 fallback 行为变化
- [ ] 测试验证：运行 `npm test` 并修复失败测试直到全绿
- [ ] 测试验证：运行 `npx tsc --noEmit` 并修复类型错误直到通过
- [ ] 测试验证：运行 `npm run dev` + `python3 test_proxy.py --count 2` 做手工联调并核对 `output.log`
- [ ] 临时文件清理：清理本次开发产生的临时调试脚本、临时日志片段与无用中间文档
- [ ] 临时文件清理：确认保留 `spec.md`、更新 `research.md`（如实现过程中有新发现）并删除无关草稿
