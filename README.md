# free-proxy

把多家免费 LLM provider 聚合成一个本地入口。先配一个 API Key，就能开始用。

## 安装 free-proxy

先把项目下载到本地：

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

然后启动服务：

```bash
uv run free-proxy serve
```

如果你刚装完，建议先这样打开网页：

```text
http://127.0.0.1:8765
```

## 升级 free-proxy

如果你已经装过这个项目，升级时在项目目录里执行：

```bash
git pull --ff-only
uv sync
```

然后重新启动：

```bash
uv run free-proxy serve
```

## 你只要记住 3 件事

1. 启动服务
2. 在网页里保存一个 API Key
3. 选一个模型开始聊天

按页面提示做这三步：

1. 保存至少一个 provider 的 API Key
2. 先选推荐模型
3. 点击验证，或者直接发一句测试消息

## 推荐怎么选

- 不确定时：`free-proxy/auto`
- 主要写代码时：`free-proxy/coding`

如果你想看排障日志，启动时加：

```bash
uv run free-proxy serve --debug
```

## 常见问题

### 页面打不开

先确认服务还在运行：

```bash
uv run free-proxy serve
```

### 没有可用模型

先换一个推荐模型再试。

### API Key 存在哪里

保存在项目根目录的 `.env` 文件里，不会提交到 GitHub。

## License

MIT
