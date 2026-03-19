# 实现计划

## 当前阶段要完成的功能

### 1. API Key 配置界面
- Web 界面输入和验证 API Key
- API Key 有效性验证（调用 OpenRouter API）
- 已配置状态的显示和修改

### 2. 模型列表显示
- 显示验证过的可用模型
- 只展示候选池内的模型（通过二次验证）

### 3. 候选池动态验证
- 启动时验证模型可用性
- 用户手工刷新模型列表
- Web 界面显示验证进度和上次更新时间

### 4. OpenClaw 配置检测
- 自动检测 OpenClaw 配置文件
- 显示配置文件状态

### 5. 一键配置到 OpenClaw
- 点击按钮自动配置
- 规则匹配修改配置文件
- 自动创建备份

### 6. 配置恢复功能
- 显示备份列表
- 一键恢复配置

### 7. 改进的降级策略
- 尝试所有候选池模型（不限制数量）
- 记录失败模型，下次跳过
- 最后尝试 openrouter/free 兜底

---

## 总览

将 7 步使用流程简化为 3 步，通过 Web 界面配置和一键配置功能降低使用门槛。

**核心目标**：
- 用户不需要理解 base_url、localhost 等技术概念
- 用户不需要手动编辑配置文件
- 配置过程可视化、可验证

---

## 功能模块

### 模块 1：API Key 配置界面

**目标**：让用户通过 Web 界面配置 API Key，并验证有效性

#### 1.1 前端界面

**文件**：`public/index.html`（新建或修改现有）

**界面元素**：
```
┌─────────────────────────────────────────┐
│  OpenRouter Free Proxy                  │
├─────────────────────────────────────────┤
│                                         │
│  OpenRouter API Key:                    │
│  ┌─────────────────────────────────────┐│
│  │ ●●●●●●●●●●●●●●●●        [获取 Key]  ││
│  └─────────────────────────────────────┘│
│           [保存并验证]                   │
│                                         │
│  状态: 未配置                            │
└─────────────────────────────────────────┘
```

**交互逻辑**：
1. 输入框类型为 `password`，打码显示
2. "获取 Key" 链接到 `https://openrouter.ai/keys`
3. "保存并验证" 按钮：
   - 点击后调用验证接口
   - 显示验证进度（"验证中..."）
   - 成功：显示 "✓ 验证成功" + 进入模块 2
   - 失败：显示具体错误信息（"API Key 无效" / "网络错误"）
4. 如果用户已配置 API Key：
   - 显示当前配置状态："已配置 (sk-****abc)"
   - 提供"修改"按钮，点击后清空输入框，允许重新输入新 Key

**状态显示**：
- 未配置：显示 "状态: 未配置"
- 已配置：显示 "状态: 已配置 (sk-****abc)"，其中 abc 显示后三位 + "修改" 按钮
- 验证中：显示 "状态: 验证中..."
- 验证失败：显示 "状态: 验证失败 - 具体原因"

#### 1.2 后端验证接口

**文件**：`src/server.ts`

**新增路由**：`POST /api/validate-key`

**验证逻辑**：
```typescript
// 伪代码
POST /api/validate-key
  Request: { apiKey: string }
  
  1. 调用 OpenRouter API 测试 Key
     GET https://openrouter.ai/api/v1/models
     Headers: Authorization: Bearer <apiKey>
  
  2. 判断响应
     - 200 OK: Key 有效
     - 401 Unauthorized: Key 无效
     - 其他: 网络错误或服务器错误
  
  3. 成功后保存到 .env 文件
     创建或追加: OPENROUTER_API_KEY=<apiKey>
  
  Response: 
    { success: true, message: "验证成功" }
    { success: false, error: "错误原因" }
```

**错误处理**：
- API Key 格式错误（不以 sk- 开头）：返回 "格式错误"
- API Key 无效（401）：返回 "API Key 无效，请检查"
- 网络错误：返回 "网络错误，请稍后重试"
- 服务器错误：返回 "服务器错误，请稍后重试"

**安全考虑**：
- API Key 不记录在日志中
- .env 文件权限设置为 600（仅所有者可读写）

#### 1.3 配置文件管理

**文件**：`src/config.ts`

**新增功能**：
- `saveApiKey(key: string)`：保存 API Key 到 .env
- `getApiKeyStatus()`：获取当前 API Key 状态（已配置/未配置）
- `maskApiKey(key: string)`：打码显示（sk-****abc）

---

### 模块 2：模型列表界面

**目标**：显示可用模型列表，提示用户可以在 OpenClaw 中使用

#### 2.1 前端界面

**在同一页面显示**：

```
┌─────────────────────────────────────────┐
│  OpenRouter Free Proxy                  │
├─────────────────────────────────────────┤
│  可用模型                               │
│  ┌─────────────────────────────────────┐│
│  │ • auto (智能降级)                    ││
│  │ • deepseek/deepseek-chat (推荐)     ││
│  │ • openai/gpt-4-turbo                ││
│  │ • ...                               ││
│  └─────────────────────────────────────┘│
│                                         │
│  在 OpenClaw 中使用:                    │
│  /model free_proxy/auto                │
└─────────────────────────────────────────┘
```

**数据来源**：
- 从现有 `/models` 接口获取
- 显示模型 ID 和说明（如 "智能降级"、"推荐"）

#### 2.2 后端数据接口

**文件**：`src/server.ts`

**现有接口**：`GET /models`（已实现）

**返回格式**：
```json
{
  "models": [
    { "id": "auto", "name": "auto", "description": "智能降级" },
    { "id": "deepseek/deepseek-chat", "name": "DeepSeek Chat", "description": "推荐" }
  ]
}
```

---

### 模块 3：一键配置到 OpenClaw

**目标**：自动检测并配置 OpenClaw，用户只需点击按钮

#### 3.1 配置文件检测

**文件**：`src/openclaw-config.ts`（新建）

**检测逻辑**：
```typescript
// 伪代码
function detectOpenClawConfig(): {
  exists: boolean,
  path: string,
  isValid: boolean,
  content?: object
}

const configPath = path.join(os.homedir(), '.openclaw', 'openclaw.json')

1. 检查文件是否存在
   - 存在：读取内容
   - 不存在：返回 { exists: false, path: configPath }

2. 检查文件是否是有效 JSON
   - 有效：解析并返回
   - 无效：返回 { exists: true, isValid: false }

3. 返回配置对象
```

#### 3.2 配置文件合并

**文件**：`src/openclaw-config.ts`

**合并逻辑**：
```typescript
// 伪代码
function mergeConfig(currentConfig: object): {
  newConfig: object,
  backup: string
}

1. 创建备份
   - 读取当前配置文件
   - 创建备份文件：openclaw.json.backup.20260319.143022
   - 返回备份文件名

2. 合并配置
   - 确保路径存在：
     models.providers.free_proxy
     agents.defaults.models
   
   - 添加 provider：
     currentConfig.models.providers.free_proxy = {
       baseUrl: "http://localhost:8765/v1",
       apiKey: "any_string",
       api: "openai-completions",
       models: [{ id: "auto", name: "auto" }]
     }
   
   - 添加 model：
     currentConfig.agents.defaults.models["free_proxy/auto"] = {}
   
   - 不修改：
     agents.defaults.model.primary
     agents.list[].model

3. 返回新配置
```

**边界情况处理**：
- 文件不存在：创建最小配置结构
- 文件存在但不是有效 JSON：报错并让用户手动处理
- 某些路径不存在（models/providers）：自动创建
- 已存在 free_proxy provider：覆盖（提醒用户）
- **安全要求**：只有验证过有效的 OpenRouter API Key 后，才能执行配置修改

**配置修改方案**：规则匹配修改
- 根据预定义规则直接修改配置文件
- 实现简单，可控性强
- 通过字段验证确保修改正确

#### 3.3 前端界面

**按钮位置**：

```
┌─────────────────────────────────────────┐
│  OpenRouter Free Proxy                  │
├─────────────────────────────────────────┤
│  OpenClaw 配置                          │
│                                         │
│  状态: ✓ 已检测到 OpenClaw              │
│  配置文件: ~/.openclaw/openclaw.json    │
│                                         │
│  [一键配置到 OpenClaw]                  │
│                                         │
│  备份管理:                              │
│  • openclaw.json.backup.20260319.143022 │
│  [恢复上一个配置]                       │
└─────────────────────────────────────────┘
```

**交互逻辑**：
1. 页面加载时检测 OpenClaw 配置文件
2. 检测到：显示配置状态 + "一键配置" 按钮
3. 未检测到：显示 "未检测到 OpenClaw 配置文件"
4. 点击按钮：
   - 显示 "正在配置..."
   - 创建备份
   - 合并配置
   - 写入文件
   - 显示 "✓ 配置成功"
   - 显示备份文件名

#### 3.4 后端接口

**文件**：`src/server.ts`

**新增路由**：`POST /api/configure-openclaw`

**请求**：无参数（从当前配置获取）

**响应**：
```json
{
  "success": true,
  "backup": "openclaw.json.backup.20260319.143022",
  "message": "配置成功"
}
```

**错误响应**：
```json
{
  "success": false,
  "error": "配置文件格式错误",
  "backup": null
}
```

---

### 模块 4：配置恢复功能

**目标**：当配置出问题时，用户可以恢复到上一个版本

#### 4.1 备份文件列表

**文件**：`src/openclaw-config.ts`

**功能**：
```typescript
// 伪代码
function listBackups(): string[]

1. 扫描 ~/.openclaw/ 目录
2. 匹配 openclaw.json.backup.* 文件
3. 按时间排序（新到旧）
4. 返回文件名列表
```

#### 4.2 恢复接口

**文件**：`src/server.ts`

**路由**：`POST /api/restore-backup`

**请求**：
```json
{
  "backup": "openclaw.json.backup.20260319.143022"
}
```

**逻辑**：
```typescript
1. 验证备份文件存在
2. 验证备份文件是有效 JSON
3. 复制备份文件到 openclaw.json
4. 返回成功
```

#### 4.3 前端界面

**元素**：
- 显示最近的备份文件：`openclaw.json.backup.20260319.143022`
- "恢复上一个配置" 按钮
- 点击后恢复并显示 "✓ 已恢复"

---

## 文件结构

### 新建文件

```
src/
├── openclaw-config.ts    # OpenClaw 配置管理
│   ├── detectOpenClawConfig()
│   ├── mergeConfig()
│   ├── listBackups()
│   └── restoreBackup()
│
public/
└── index.html            # Web 界面（新建或修改现有）
    ├── API Key 输入区域
    ├── 模型列表区域
    ├── OpenClaw 配置区域
    └── 备份管理区域
```

### 修改文件

```
src/
├── server.ts             # 添加路由
│   ├── POST /api/validate-key
│   ├── POST /api/configure-openclaw
│   └── POST /api/restore-backup
│
├── config.ts             # 添加功能
│   ├── saveApiKey()
│   ├── getApiKeyStatus()
│   └── maskApiKey()
```

---

## 实现顺序

### 阶段 1：API Key 配置（基础功能）

**目标**：用户可以通过 Web 配置 API Key

**步骤**：
1. 实现 `config.ts` 的 API Key 管理功能
2. 实现 `server.ts` 的 `/api/validate-key` 接口
3. 实现前端界面（API Key 输入 + 验证）
4. 测试：输入正确/错误的 Key，验证是否正确保存

**交付物**：
- 用户可以输入 API Key
- Key 会被验证
- 验证成功后保存到 .env
- 界面显示验证状态

### 阶段 2：模型列表显示

**目标**：用户可以看到可用模型

**步骤**：
1. 创建推荐模型列表 `src/recommended-models.ts`
2. 修改 `GET /models` 接口，只返回推荐模型 + 添加 description 字段
3. 实现前端模型列表显示
4. 测试：验证模型列表正确显示

**交付物**：
- 用户可以看到推荐模型
- 每个模型有简单说明

### 阶段 X：模型可用性优化

**目标**：提供可靠的模型选择、智能的降级策略和动态验证机制

**步骤**：
1. 创建候选池管理模块 `src/candidate-pool.ts`
   - 实现模型可用性验证逻辑
   - 实现候选池更新和缓存机制
   - 实现失败模型记录功能
2. 修改 `GET /models` 接口
   - 返回候选池内的模型（只返回验证过的模型）
   - 添加 description 字段
3. 修改降级逻辑 `src/fallback.ts`
   - 从候选池获取所有模型（不限制数量）
   - 尝试所有候选模型
   - 记录失败模型
   - 最后尝试 `openrouter/free` 兜底
4. 实现 Web 界面模型刷新功能
   - "刷新模型列表"按钮
   - 显示"上次更新时间"
   - 显示验证进度
5. 测试：模拟不可用模型场景，验证降级策略

**交付物**：
- 候选池管理模块（验证、缓存、更新）
- Web 界面只显示验证过的模型
- 尝试所有候选模型的降级策略
- 失败模型记录功能

### 阶段 3：OpenClaw 配置检测

**目标**：自动检测 OpenClaw 配置文件

**步骤**：
1. 实现 `openclaw-config.ts` 的检测功能
2. 实现 `server.ts` 的 `/api/detect-openclaw` 接口
3. 实现前端检测状态显示
4. 测试：有/无配置文件时的表现

**交付物**：
- 自动检测 OpenClaw 配置
- 显示检测状态

### 阶段 4：一键配置

**目标**：用户点击按钮完成配置

**步骤**：
1. 实现 `openclaw-config.ts` 的合并功能
2. 实现 `server.ts` 的 `/api/configure-openclaw` 接口
3. 实现前端一键配置按钮
4. 测试：各种边界情况

**交付物**：
- 用户可以一键配置
- 配置文件正确更新
- 自动创建备份

### 阶段 5：配置恢复

**目标**：用户可以恢复配置

**步骤**：
1. 实现 `openclaw-config.ts` 的备份管理功能
2. 实现 `server.ts` 的 `/api/restore-backup` 接口
3. 实现前端备份管理和恢复功能
4. 测试：恢复操作

**交付物**：
- 用户可以查看备份列表
- 用户可以恢复配置

---

## 测试验证

### 单元测试

**文件**：`tests/` 目录

**测试用例**：
1. API Key 验证
   - 有效 Key
   - 无效 Key
   - 格式错误
   - 网络错误

2. OpenClaw 配置检测
   - 文件存在且有效
   - 文件不存在
   - 文件存在但无效

3. 配置合并
   - 正常合并
   - 文件不存在创建
   - 路径不存在创建
   - 已存在 provider 覆盖

### 集成测试

**场景**：
1. 完整流程：输入 Key → 验证 → 显示模型 → 配置 OpenClaw
2. 边界场景：
   - OpenClaw 未安装
   - 配置文件损坏
   - 已配置过 free_proxy

### 手动测试

**步骤**：
1. 启动代理服务：`npm start`
2. 打开浏览器：`http://localhost:8765`
3. 输入 OpenRouter API Key
4. 验证状态显示
5. 查看模型列表
6. 点击"一键配置到 OpenClaw"
7. 打开 OpenClaw，执行 `/model free_proxy/auto`
8. 发送消息测试

---

## 注意事项

### 安全考虑

1. **API Key 保护**
   - 密码框输入
   - 不记录到日志
   - .env 文件权限 600

2. **配置文件备份**
   - 备份文件也包含敏感信息
   - 不暴露到 Web 界面
   - 仅显示文件名

3. **输入验证**
   - API Key 格式验证
   - 文件路径验证（防止路径注入）

### 错误处理

1. **网络错误**
   - 提示用户重试
   - 显示具体错误信息

2. **文件错误**
   - 配置文件损坏：提示用户手动修复
   - 写入失败：提示权限问题

3. **边界情况**
   - OpenClaw 未安装：显示安装指引链接
   - 配置文件已存在 free_proxy：提醒用户确认覆盖

### 兼容性

1. **Node.js 版本**：确保代码兼容 Node.js 14+
2. **操作系统**：测试 macOS、Linux、Windows
3. **OpenClaw 版本**：确认配置格式兼容性

---

## 实际问题讨论

### 问题 1：很多 Free 模型实际不可用

**现象**：OpenRouter 列出的 free 模型很多，但实际可用的不多。列出很多不可用的模型，用户尝试后会感觉工具是坏的。

**解决方案**：

**方案 A：动态验证模型池（推荐且必要）**

1. **模型二次验证流程**：
   - OpenRouter 返回 free 模型列表
   - 对每个模型进行可用性验证（测试调用）
   - 验证通过的模型进入候选池
   - 只展示和使用候选池内的模型

2. **候选池更新机制**：
   - **启动时验证**：npm start 时自动验证一次
   - **用户手工刷新**：Web 界面提供"刷新模型列表"按钮
   ```typescript
   // src/candidate-pool.ts
   const CANDIDATE_POOL: Map<string, ModelInfo> = new Map();
   
   async function refreshCandidatePool() {
     const freeModels = await fetchFreeModels();
     for (const model of freeModels) {
       const isValid = await validateModel(model.id);
       if (isValid) {
         CANDIDATE_POOL.set(model.id, model);
       }
     }
   }
   ```

3. **Web 界面交互**：
   - 显示"上次更新时间：2026-03-19 14:30"
   - 提供"刷新模型列表"按钮
   - 刷新时显示进度："正在验证模型可用性... (3/10)"

4. **降级策略**：
   - 在候选池内的模型中进行降级
   - 尝试所有候选模型后才提示用户无可用模型

**优点**：
- 动态更新，无需人工维护列表
- 确保列出的模型都是可用的
- 用户可控制更新频率

**缺点**：
- 启动时需要验证时间（可在后台异步进行）
- 验证可能增加 OpenRouter API 调用次数

**独立数据模块**：`src/candidate-pool.ts`
```typescript
// src/candidate-pool.ts
export interface CandidateModel {
  id: string;
  name: string;
  lastValidated: Date;
  successRate: number;
}

export class CandidatePool {
  private models: Map<string, CandidateModel> = new Map();
  private lastUpdateTime: number = 0;
  
  // 验证模型可用性
  async validateModel(modelId: string): Promise<boolean>;
  
  // 刷新候选池
  async refresh(force?: boolean): Promise<void>;
  
  // 获取候选模型列表
  getCandidates(): CandidateModel[];
  
  // 标记模型失败
  markModelFailed(modelId: string): void;
}
```

### 问题 2：降级策略可能导致过早 fallback

**现象**：当前降级策略只尝试前 3 个免费模型，如果都失败就结束，而不是尝试所有候选模型。

**当前降级逻辑**（已检查 src/fallback.ts）：
```typescript
// 当前实现（第23行）
for (const { model } of ranked.slice(0, 3)) {  // 只取前 3 个
  if (!chain.includes(model.id)) {
    chain.push(model.id);
  }
}

// 降级链组成（第11-37行）
// 1. preferredModel（用户指定的模型）
// 2. 前 3 个免费模型
// 3. openrouter/free（兜底）
// 4. 尝试所有模型后抛出错误
```

**问题**：
- 如果前 3 个模型都不可用，就直接 fallback 到 `openrouter/free` 或报错
- 没有尝试所有候选模型
- 用户看不到哪些模型真的不可用

**解决方案**：

**方案 A：尝试所有候选模型 + 记录失败模型**

1. **修改降级逻辑**：
   - 从候选池获取所有可用模型
   - 尝试所有候选模型，而不是只试前 3 个
   - 记录失败的模型，下次优先跳过
   
   ```typescript
   // 改进逻辑
   const candidateModels = candidatePool.getCandidates();
   const failedModels = new Set<string>();
   
   for (const model of candidateModels) {
     if (failedModels.has(model.id)) {
       continue; // 跳过已失败的模型
     }
     
     try {
       const result = await execute(model.id);
       return result;
     } catch (error) {
       failedModels.add(model.id);
       candidatePool.markModelFailed(model.id);
       continue;
     }
   }
   
   // 所有候选模型都失败了
   throw new Error("当前时段无可用模型，请稍后重试");
   ```

2. **失败模型记录**：
   - 内存记录：当前运行期间速记
   - 过期机制：失败记录保留一定时间后清除

**本期采用**：
- 尝试所有候选模型（不限制数量）
- 记录失败模型，下次跳过
- 最后尝试 `openrouter/free` 作为兜底
- 不显示复杂错误详情，简化用户体验

### 实现计划调整

**新增功能**：
1. 候选池管理模块（`src/candidate-pool.ts`）
2. 失败模型记录（内存）
3. 改进的降级策略

**调整后的阶段**：

**阶段 X：模型可用性优化**（在阶段 2 之后）

**步骤**：
1. 创建推荐模型列表（需要研究和验证）
2. 修改 `/models` 接口，只返回推荐模型
3. 修改降级逻辑，增加重试次数和错误信息
4. 添加失败模型记录功能
5. 测试：模拟不可用模型场景

**交付物**：
- 候选池管理模块（验证、缓存、更新）
- Web 界面只显示验证过的模型
- 尝试所有候选模型的降级策略
- 失败模型记录功能

---

## 时间估算

| 阶段 | 工作内容 | 预计时间 |
|------|----------|----------|
| 阶段 1 | API Key 配置 | 2-3 小时 |
| 阶段 2 | 模型列表显示 | 1 小时 |
| 阶段 X | 模型可用性优化 | 2-3 小时 |
| 阶段 3 | OpenClaw 检测 | 1-2 小时 |
| 阶段 4 | 一键配置 | 2-3 小时 |
| 阶段 5 | 配置恢复 | 1-2 小时 |
| 测试 | 单元测试 + 集成测试 | 2-3 小时 |
| **总计** | | **11-17 小时** |

---

## 风险点

1. **OpenClaw 配置格式变化**
   - 风险：OpenClaw 更新后配置格式可能改变
   - 应对：监控 OpenClaw 更新，必要时调整

2. **跨平台路径问题**
   - 风险：Windows 路径分隔符不同
   - 应对：使用 `path.join()` 处理路径

3. **API Key 验证失败处理**
   - 风险：验证接口不稳定
   - 应对：提供重试机制，记录错误日志

4. **配置文件权限**
   - 风险：用户没有写入权限
   - 应对：捕获错误并提示用户

---

## 用户视角流程（最终）

### 新用户（第一次使用）

1. `git clone <repo> && cd <repo>`
2. `npm install && npm start`
3. 打开 `http://localhost:8765`
4. 输入 OpenRouter API Key，点击"保存并验证"
5. 点击"一键配置到 OpenClaw"
6. 打开 OpenClaw，执行 `/model free_proxy/auto`
7. 开始使用

**步骤减少**：从 7 步到 3 步（实质交互）
**概念简化**：不需要理解 base_url、配置文件位置

### 老用户（已配置过）

1. `npm start`
2. 打开 `http://localhost:8765`
3. 点击"更新配置"（如有新版本）
4. 切换模型使用

**场景**：主要是查看模型列表和状态

---

## TODO List

### 阶段 1：API Key 配置（基础功能）

- [x] 后端开发
  - [x] 实现 `src/config.ts`
    - [x] `saveApiKey(key: string)` - 保存 API Key 到 .env
    - [x] `getApiKeyStatus()` - 获取当前 API Key 状态
    - [x] `maskApiKey(key: string)` - 打码显示
  - [x] 实现 `src/server.ts` 路由
    - [x] `POST /api/validate-key` - 验证 API Key 并保存
    - [x] 调用 OpenRouter API 测试 Key 有效性
    - [x] 错误处理（格式错误、无效、网络错误）

- [x] 前端开发
  - [x] 实现 `public/index.html`
    - [x] API Key 输入框（password 类型）
    - [x] "获取 Key" 链接
    - [x] "保存并验证" 按钮
    - [x] 状态显示区域（未配置/已配置/验证中/验证失败）
    - [x] 已配置状态下的"修改"按钮

- [ ] 测试
  - [ ] 有效 API Key 输入和验证
  - [ ] 无效 API Key 输入和验证
  - [ ] API Key 格式错误处理
  - [ ] 网络错误处理
  - [ ] .env 文件权限设置（600）

### 阶段 2：模型列表显示

- [x] 后端开发
  - [x] 修改 `GET /models` 接口
    - [x] 添加 description 字段
    - [x] 简化返回格式

- [x] 前端开发
  - [x] 实现模型列表显示
    - [x] 从 `/models` 接口获取数据
    - [x] 显示模型 ID 和说明
    - [x] 显示使用提示 `/model free_proxy/auto`

- [ ] 测试
  - [ ] 验证模型列表正确显示
  - [ ] 验证 description 字段正确显示

### 阶段 X：模型可用性优化

- [x] 后端开发
  - [x] 创建 `src/candidate-pool.ts`
    - [x] `validateModel(modelId: string)` - 验证模型可用性
    - [x] `refresh()` - 刷新候选池
    - [x] `getCandidates()` - 获取候选模型列表
    - [x] `markModelFailed(modelId: string)` - 标记失败模型
    - [x] 在内存中维护候选池 Map
  - [x] 修改 `GET /models` 接口
    - [x] 返回候选池内的模型
    - [x] 启动时自动验证一次
  - [x] 修改 `src/fallback.ts`
    - [x] 从候选池获取所有模型（移除 `.slice(0, 3)` 限制）
    - [x] 尝试所有候选模型
    - [x] 记录失败模型到候选池
    - [x] 最后尝试 `openrouter/free` 兜底

- [x] 前端开发
  - [x] 实现模型刷新功能
    - [x] "刷新模型列表" 按钮
    - [x] 显示"上次更新时间"
    - [x] 显示验证进度 "正在验证模型可用性... (3/10)"

- [ ] 测试
  - [ ] 模拟不可用模型场景
  - [ ] 验证降级策略（尝试所有候选模型）
  - [ ] 验证失败模型记录
  - [ ] 验证候选池刷新功能

### 阶段 3：OpenClaw 配置检测

- [x] 后端开发
  - [x] 创建 `src/openclaw-config.ts`
    - [x] `detectOpenClawConfig()` - 检测配置文件
    - [x] 检查 `~/.openclaw/openclaw.json` 是否存在
    - [x] 验证 JSON 格式是否有效
  - [x] 实现 `src/server.ts` 路由
    - [x] `GET /api/detect-openclaw` - 返回配置文件状态

- [x] 前端开发
  - [x] 实现检测状态显示
    - [x] 显示"已检测到 OpenClaw" 或 "未检测到 OpenClaw"
    - [x] 显示配置文件路径

- [ ] 测试
  - [ ] 有配置文件时的表现
  - [ ] 无配置文件时的表现
  - [ ] 配置文件损坏时的表现

### 阶段 4：一键配置

- [x] 后端开发
  - [x] 完善 `src/openclaw-config.ts`
    - [x] `mergeConfig()` - 合并配置
    - [x] 创建备份文件
    - [x] 添加 free_proxy provider
    - [x] 添加 free_proxy/auto 模型
    - [x] 不修改用户的默认模型配置
    - [x] 处理边界情况（文件不存在、JSON 格式错误等）
  - [x] 实现 `src/server.ts` 路由
    - [x] `POST /api/configure-openclaw` - 执行配置
    - [x] 验证 API Key 有效性（前置条件）
    - [x] 返回备份文件名

- [x] 前端开发
  - [x] 实现一键配置按钮
    - [x] 点击前显示确认提示
    - [x] 显示"正在配置..."
    - [x] 显示"✓ 配置成功"
    - [x] 显示备份文件名

- [ ] 测试
  - [ ] 无配置文件时创建
  - [ ] 有配置文件时合并
  - [ ] 配置文件损坏时报错
  - [ ] 已存在 free_proxy 时覆盖（提醒）
  - [ ] 备份文件创建
  - [ ] API Key 未验证时禁止配置

### 阶段 5：配置恢复

- [x] 后端开发
  - [x] 完善 `src/openclaw-config.ts`
    - [x] `listBackups()` - 列出备份文件
    - [x] `restoreBackup(backup: string)` - 恢复备份
  - [x] 实现 `src/server.ts` 路由
    - [x] `GET /api/backups` - 获取备份列表
    - [x] `POST /api/restore-backup` - 恢复指定备份

- [x] 前端开发
  - [x] 实现备份管理界面
    - [x] 显示最近的备份文件
    - [x] "恢复上一个配置" 按钮
    - [x] 确认恢复提示
    - [x] 显示"✓ 已恢复"

- [ ] 测试
  - [ ] 备份文件列表
  - [ ] 恢复操作
  - [ ] 恢复后配置文件验证

### 最终测试

- [ ] 单元测试
  - [ ] API Key 验证（有效、无效、格式错误、网络错误）
  - [ ] OpenClaw 配置检测（存在、不存在、格式错误）
  - [ ] 配置合并（正常、创建、路径不存在、覆盖）

- [ ] 集成测试
  - [ ] 完整流程：输入 Key → 验证 → 显示模型 → 配置 OpenClaw
  - [ ] 边界场景：OpenClaw 未安装、配置文件损坏、已配置过 free_proxy

- [ ] 手动测试
  - [ ] 启动服务：`npm start`
  - [ ] 打开浏览器：`http://localhost:8765`
  - [ ] 输入 OpenRouter API Key
  - [ ] 验证状态显示
  - [ ] 查看模型列表
  - [ ] 刷新模型列表
  - [ ] 点击"一键配置到 OpenClaw"
  - [ ] 打开 OpenClaw，执行 `/model free_proxy/auto`
  - [ ] 发送消息测试
  - [ ] 恢复配置备份