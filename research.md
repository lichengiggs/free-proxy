# 降低使用门槛研究

## 问题分析

### 当前使用流程（7步）

1. git clone 仓库
2. npm install 安装依赖
3. 创建 .env 填入 API Key
4. npm start 启动服务
5. 打开 localhost:8765 选模型
6. 在 OpenClaw 里配 base_url/api_key/model
7. 开始使用

### 小白用户的痛点

- **概念障碍**：base_url 是什么？localhost:8765/v1 是什么意思？
- **配置位置**：OpenClaw 配置在哪？怎么改？
- **命令行恐惧**：npm、git 对非技术用户是门槛
- **多工具协调**：要同时操作代理和客户端

## 整合方案

### 学习项目场景（最简化）

如果只是自己学习项目，不需要复杂安装流程：

```bash
git clone <repo>
cd <repo>
npm install
npm start
```

就这么简单。

**关于启动方式**：
- `npm start` 是开发时的启动方式，前台运行，方便看到日志
- `free-proxy start` 是后续封装的命令，后台运行，生产环境用
- 学习阶段直接用 `npm start` 即可
- 两者是同一个服务，只是运行模式不同

### Web 界面配置

**场景1：已配置 API Key**
- 显示模型列表
- 检测 OpenClaw 配置文件（~/.openclaw/openclaw.json）
- 如果检测到，显示"一键配置到 OpenClaw"按钮

**场景2：未配置 API Key**
- 显示输入框让用户填入 OpenRouter API Key
- 输入框打码显示（密码框）
- 提供"获取 API Key"链接到 openrouter.ai/keys
- **API Key 验证**：保存前先调用 OpenRouter API 测试 Key 是否有效，无效则提示具体错误
- 验证成功后才保存

### OpenClaw 配置结构

**配置文件位置**：`~/.openclaw/openclaw.json`

**需要修改的两处**：

1. `models.providers` - 添加 free_proxy provider
2. `agents.defaults.models` - 添加可用模型

**最简配置**（只写必须的字段）：

```json
// 添加到 models.providers
"free_proxy": {
  "baseUrl": "http://localhost:8765/v1",
  "apiKey": "any_string",
  "api": "openai-completions",
  "models": [
    { "id": "auto", "name": "auto" }
  ]
}
```

```json
// 添加到 agents.defaults.models
"free_proxy/auto": {}
```

就这样，其他字段（contextWindow、maxTokens 等）都可以省略，OpenClaw 会用默认值。

### 一键配置流程

**配置原则**：
- 只添加 provider 和 model，不修改用户现有的默认模型配置
- 不触碰 `agents.defaults.model.primary` 和 `agents.list[].model`
- 让用户自己在 OpenClaw 里切换模型

**情况1：用户已有配置**

只添加上述两处配置，智能合并到现有文件中。

**情况2：用户配置文件为空或不存在**

创建最小配置文件，只包含必要的部分。

**情况3：配置文件不完整**

智能合并，自动创建缺失的字段路径。

### 备份管理

- 每次修改前自动备份：openclaw.json.backup.YYYYMMDD.HHMMSS
- Web 界面显示备份列表
- 提供"恢复上一个配置"按钮

## 最终使用流程（3步）

1. **启动**：git clone + npm install + npm start
2. **配置 API Key**：Web 界面输入（自动验证有效性）
3. **配置 OpenClaw**：Web 界面点击"一键配置"

用户在 OpenClaw 中通过 `/model free_proxy/auto` 切换模型。

搞定。

## 注意

- 不考虑图形界面（桌面应用），跟工具用途不符合
- 核心是让用户不用理解 base_url，不用手动改配置
- 让小白用户尽可能简单，能简单的步骤就别让人家操心
- 第一期只解决 OpenClaw，其他客户端以后再说
- **不修改用户默认模型配置**，只添加 provider 和 model 供用户选择
- API Key 需要在保存前验证有效性
- 配置越简单越好，只写必须的字段
