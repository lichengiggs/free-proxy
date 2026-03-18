# OpenRouter Free Proxy

本地 OpenRouter 免费模型代理，特点是**自动降级**——你选的模型限流时自动换别的免费模型。

## 安装

```bash
git clone <repository-url>
cd or_free_proxy
npm install
```

## 配置

创建 `.env` 文件：

```env
OPENROUTER_API_KEY=your_key_here
```

获取 API Key: https://openrouter.ai/keys

## 启动

```bash
npm start
```

访问 http://localhost:8765 查看模型列表和切换默认模型。

## 使用

把编码工具的 Base URL 改成：

```
http://localhost:8765/v1
```

API Key 随意填，模型名也随意填（代理会自动用你在 Web 界面选的模型）。

### OpenCode 示例

```bash
/config set base_url http://localhost:8765/v1
/config set api_key xxx
/config set model xxx
```

## 自动降级

如果首选模型返回 429（限流）或 503（不可用），代理会自动尝试其他免费模型。响应头 `X-Actual-Model` 告诉你实际用了哪个模型。

降级顺序：首选模型 → 评分前3的免费模型 → openrouter/free（兜底）

## 测试

```bash
npm test          # 单元测试
python3 test_proxy.py  # 实际验证（循环10次）
```

## 许可证

MIT
