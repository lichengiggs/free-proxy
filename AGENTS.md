# AGENTS.md

## 项目经验总结

### 1. 架构原则

**最小有效剂量**：只实现当前必需的功能，不为假设的未来场景做过度设计。

**KISS 原则**：保持简单。复杂的抽象层往往比直接代码更难维护。

### 2. 本次开发教训

#### API Key 管理
- 存储位置：`.env` 放在项目根目录（而非 home 子目录），便于测试和用户理解
- 安全：绝不在 Git 中提交真实 key，`.gitignore` 必须包含 `.env`

#### OpenClaw 配置
- 路径：使用 `~/.openclaw/openclaw.json`（绝对路径）
- 检测失败时：提供手动输入路径的选项
- 备份：修改前自动创建时间戳备份

#### 模型可用性
- 不要信任 OpenRouter 返回的免费模型列表
- 必须二次验证：测试调用 API 确认模型真的可用
- 候选池：内存中维护，启动时验证 + 用户手动刷新

#### 测试策略
- TDD 是好习惯，但测试文件要和实现同步更新
- ESM 模式下测试不能用 `require('fs')`，必须用顶层 `import`
- 模拟外部 API 时，测试期望要和实际 HTTP 状态码一致

### 3. 代码规范

**不要：**
- 添加不必要的 JSDoc 注释
- 使用 `any` 类型
- 过度工程化的抽象层

**要：**
- 注释解释 "Why" 而非 "What"
- 强制处理边界条件（null、空数组、网络错误）
- 错误信息对小白友好（不暴露技术细节）

### 4. 调试技巧

```bash
# 检查端口占用
lsof -i :8765

# 查看服务日志
npm start 2>&1 | tail -50

# 测试 API
curl -X POST http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"hi"}]}'
```

### 5. 发布 checklist

- [ ] 删除 `.env`, `config.json`, `rate-limit-state.json`
- [ ] 检查 `git log` 中无 API key
- [ ] 更新 README.md
- [ ] 运行 `npm test`（确保不报错）
- [ ] 运行 `npx tsc --noEmit`（类型检查通过）