# Python Provider Core 重构设计

## 目标

把 `free-proxy` 从“TS 迁移后继续叠加”的状态，收敛成一个以 Python 为唯一主线的产品化项目。

本次重构只聚焦核心 provider 链路，目标是让代码更容易维护、排查和继续产品化，不做功能扩张。

## 背景问题

当前项目存在三个结构性问题：

1. 历史 TS 代码仍在仓库中存在感很强，容易让人误判主线。
2. Python 主链路里，provider 元数据、路由、fallback、健康状态、token 预算、HTTP 返回格式混在一起。
3. `server.py` 过厚，既像控制器又像策略层，后续改动成本高。

## 范围

### 必做

- 以 `python_scripts/provider_catalog.py` 作为唯一 provider 元数据来源。
- 拆分 provider 核心职责：catalog、router/policy、adapter/transport、state。
- 让 `python_scripts/server.py` 只保留 HTTP 路由与响应转换。
- 清理 TS 主线引用，停止让 `src/providers/*` 参与运行路径。
- 保留必要测试，覆盖重构后的关键行为。

### 暂不做

- 新增 provider。
- 重做前端界面。
- 改变对外产品定位。
- 追求“全仓库一次性大扫除”。

## 推荐架构

### 1) Provider Catalog

职责：保存 provider 名称、base URL、API key 环境变量、协议格式、模型提示信息。

唯一数据源：`python_scripts/provider_catalog.py`。

### 2) Provider Policy / Router

职责：

- 解析用户输入的模型别名或 `provider/model`。
- 决定候选 provider 与候选模型顺序。
- 执行 fallback 选择。
- 读取健康状态与 token limit 状态。

要求：该层只做决策，不直接拼 HTTP 响应。

### 3) Provider Adapter / Transport

职责：

- 负责向上游发送请求。
- 负责不同 provider 协议差异的最小转换。
- 不承担业务级 fallback 决策。

要求：若 provider 协议不一致，差异必须收敛到 adapter，不向上层扩散。

### 4) HTTP Server

职责：

- 解析请求。
- 调用 service。
- 组装 OpenAI 兼容响应。
- 返回统一错误格式。

要求：HTTP 层不再保存 provider 选择规则。

## 迁移策略

### 阶段 1：收口主线

- 明确 Python 是唯一运行入口。
- 解除 TS provider 代码与主流程的关联。
- 保留历史文档，但不再允许其参与决策。

### 阶段 2：拆分核心职责

- 从 `service.py` 中抽离 router/policy。
- 把聊天执行、候选选择、健康状态更新分成更小的模块。
- 把 `server.py` 中的复杂分支下放到 service。

### 阶段 3：清理冗余

- 删除不再使用的 TS 运行代码、脚本和配置。
- 删除中间产物与无意义的遗留文件。
- 保留必要测试和长期文档。

## 验收标准

- 仓库主运行路径只保留 Python 主链路。
- provider 元数据只有一个权威来源。
- `server.py` 体积明显收缩，职责单一。
- provider 路由与 fallback 的行为可以通过测试单独验证。
- 旧 TS 目录不再影响运行结果。

## 风险

- 外部调用方如果依赖旧行为，可能会感知到接口变化。
- provider 选择规则收敛时，少数边缘模型可能需要重新校准。
- 历史遗留文件删除前，需要确认不再被测试或文档引用。

## 建议实施顺序

1. 先拆 provider 核心边界。
2. 再瘦身 HTTP 层。
3. 然后清理 TS 遗留和无用文件。
4. 最后补回归测试与文档。
