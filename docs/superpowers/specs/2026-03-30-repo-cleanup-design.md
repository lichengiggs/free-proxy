# 仓库主线收紧与垃圾文件清理设计

## 1. 目标

把仓库收口为“当前 Python 主线的最小可信集合”：

- 只保留当前运行必需代码与长期有效文档
- 删除过程文档、失真文档、历史遗留说明与本地输出物
- 把运行时状态移出版本库，但保留本地运行能力
- 用 `.gitignore` 和长期文档封堵同类污染再次进入主分支

本次工作是清理与边界收口，不做功能重构。

## 2. 已验证现状

### 2.1 当前主线

- 当前唯一运行主线是 `python_scripts/`
- `docs/research.md` 已承担当前结构说明
- README 末尾仍引用历史文档：
  - `docs/typescript-legacy.md`
  - `docs/migration-python-mainline.md`

### 2.2 已确认的过程/失真文档

以下文件不应继续作为长期资产保留：

- `docs/superpowers/plans/2026-03-26-readme-refresh.md`
  - 属于未完成执行计划
  - 与仓库规则“过程文档完成后应清理”冲突
- `docs/superpowers/specs/2026-03-30-python-provider-core-refactor-design.md`
  - 把已完成分层继续写成“待做重构”
  - 仍提到已不存在的 `src/providers/*`
- `docs/typescript-legacy.md`
  - 用户已明确不保留历史档案
- `docs/migration-python-mainline.md`
  - 与 `docs/research.md` 存在职责重叠；用户要求历史迁移文档不再单独保留

### 2.3 已确认的运行时/本地输出物

以下文件对本地运行有帮助，但不应入库：

- `data/model-health.json`
  - 运行时健康快照
  - 会过期，且已被 review 指出容易在提交时失效
- `data/token-limits.json`
  - 运行时学习状态
  - 当前内容仅为 `{}`，没有长期知识价值
- `output.log`
  - 典型本地输出物

### 2.4 当前封堵不足

当前 `.gitignore` 只覆盖通用日志和少量状态文件，未明确覆盖：

- `data/model-health.json`
- `data/token-limits.json`
- 其他同类运行时快照/缓存

## 3. 清理原则

### 3.1 保留

仅保留同时满足以下条件的文件：

1. 当前 Python 主线运行或验证必需
2. 面向用户当前使用路径必需
3. 内容稳定、可审查、跨机器一致

### 3.2 删除

删除以下类别：

- 过程性文档（plan、执行草稿）
- 与当前架构冲突的 spec / 说明
- 已废弃历史文档
- 本地输出、调试残留、临时文件

### 3.3 忽略但不废弃

下列文件保留运行价值，但改为本地生成并加入 `.gitignore`：

- 健康快照
- token limit 学习状态
- 其他运行期缓存/探测结果
- 本地日志

## 4. 方案比较

### 方案 A：激进收口（推荐）

- 删除所有已确认的过程/失真/历史文档
- 仅保留 `docs/research.md` 作为长期技术总览
- 移除已入库运行时状态文件
- 更新 `.gitignore` 与长期文档规则

优点：

- 与用户目标完全一致
- 仓库边界最清晰
- 后续 review 成本最低

缺点：

- 需要同步更新 README / research 中的历史引用

### 方案 B：保守收口

- 只删运行时文件和输出物
- 历史文档继续保留

缺点：

- 无法解决“文档误导主线”的核心问题
- 与用户已确认方向冲突

## 5. 设计决策

采用 **方案 A：激进收口**。

### 5.1 文档结构决策

- `docs/research.md` 是唯一长期技术总览
- 删除分散旧 spec / plan / migration / legacy 文档
- README 不再引用已删除历史文档；只引用当前主线事实

### 5.2 data 目录决策

- `data/` 只保留稳定静态事实文件
- `data/model-health.json`、`data/token-limits.json` 改为本地运行时文件
- 代码继续使用这些路径，但仓库不再版本化其内容

### 5.3 回潮封堵决策

- `.gitignore` 明确忽略运行时状态与输出物
- `AGENTS.md` 明确：运行时学习/探测/健康状态不得入库
- `docs/research.md` 明确：哪些 `data/` 文件是静态事实，哪些是本地状态

## 6. 实施范围

### 必做

1. 删除：
   - `docs/superpowers/plans/2026-03-26-readme-refresh.md`
   - `docs/superpowers/specs/2026-03-30-python-provider-core-refactor-design.md`
   - `docs/typescript-legacy.md`
   - `docs/migration-python-mainline.md`
   - `output.log`
   - `data/model-health.json`
   - `data/token-limits.json`
2. 更新：
   - `.gitignore`
   - `README.md`
   - `README_EN.md`
   - `AGENTS.md`
   - `docs/research.md`
3. 验证：
   - 搜索仓库中对已删除文档和运行时文件的失效引用
   - 确认测试仍可通过，且不会因缺少已入库快照而失败

### 不做

- 不重构 Python 运行逻辑
- 不新增配置机制
- 不为历史路径做兼容文档层保留
- 不处理与本次清理无关的代码风格问题

## 7. 风险与约束

### 风险 1：删除运行时状态后，首次本地运行缺少文件

处理：

- 依赖现有 store 逻辑按需创建文件
- 若现有逻辑不自动创建，再补最小初始化处理，但仅在必要时做

### 风险 2：测试或文档仍引用已删除文件

处理：

- 先全局搜索引用再删除
- 更新 README / tests 中的历史引用

### 风险 3：误删静态事实文件

处理：

- 只删除已确认属于运行时状态的 `model-health.json` / `token-limits.json`
- `models.dev.json` 这类大但稳定的静态元数据暂不动

## 8. 验收标准

完成后需满足：

1. 仓库中不再存在过程性计划文档和失真架构 spec
2. 仓库中不再版本化运行时健康/学习状态
3. 根目录不再保留本地输出物
4. README / research / AGENTS 对主线和 data 分类表述一致
5. 当前 Python 主线测试通过
6. `docs/research.md` 成为唯一长期技术总览

