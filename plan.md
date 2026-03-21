# UI 调整实现计划

## 目标

本次只做前端 UI/交互调整，不改核心后端路由和回退链逻辑。目标是：

1. 将配置供应商区改成类似“选择模型”的卡片布局，减少纵向滚动。
2. 去掉“选择模型”里的“验证模型”动作，用户点到什么模型就直接切什么模型。
3. 缩小模型列表中文字尺寸，提升单屏可见数量，减少滚动。

核心前提：后端已有 fallback 策略兜底，因此前端不再承担“先验证再选择”的职责。

---

## 现状判断

根据 `research.md`，当前页面主要问题有两个：

- Provider 配置区是纵向堆叠的大块表单，8 个 Provider 会拉长页面。
- 模型选择区里存在“验证并添加”这类前置确认流程，和当前 fallback 机制重复。
- 模型名称、ID、状态等文案占位较大，导致一屏显示的模型数量偏少。

---

## 修改范围

### 需要改的文件

- `public/index.html`
- 如有内联脚本：同文件内的 `script` 区块

### 不需要改的文件

- `src/fallback.ts`
- `src/provider-health.ts`
- `src/candidate-pool.ts`

原因：问题重点在 UI 和交互层，后端回退已能覆盖“模型不可用”的情况。

---

## 实现方案

### 1) Provider 配置区改成卡片式网格

#### 设计

- 从“纵向大表单”改成“横向卡片网格”。
- 每个 Provider 卡片只保留最关键内容：名称、状态、API Key 输入、保存按钮。
- 次要操作（说明链接、折叠详情）放到卡片底部或次级区域。
- 桌面端 2~4 列自适应，移动端 1 列。

#### 关键结构示意

```html
<section class="provider-section">
  <div class="section-header">
    <h2>配置供应商</h2>
    <p>按卡片快速配置，不再拉长页面</p>
  </div>

  <div id="providerGrid" class="provider-grid">
    <!-- 由 JS 渲染 provider-card -->
  </div>
</section>
```

#### 卡片模板示意

```html
<article class="provider-card">
  <div class="provider-card__top">
    <div>
      <h3>OpenRouter</h3>
      <span class="provider-badge provider-badge--free">免费</span>
    </div>
    <span class="provider-status is-ready">已配置</span>
  </div>

  <label class="field-label" for="openrouterKey">API Key</label>
  <input id="openrouterKey" class="input input--compact" type="password" />

  <div class="provider-card__actions">
    <button class="btn btn-primary btn-sm">保存</button>
    <button class="btn btn-ghost btn-sm">修改</button>
  </div>
</article>
```

#### 关键样式方向

```css
.provider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.provider-card {
  border-radius: 14px;
  padding: 14px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
}

.input--compact {
  height: 34px;
  font-size: 12px;
}
```

#### 交互要点

- 继续沿用现有保存/掩码/状态刷新逻辑。
- 只是把 DOM 组织方式从“纵向区块”换成“卡片网格”。
- 如果原来有“获取 Key 链接”，建议收进卡片底部的小字链接，避免卡片过高。

---

### 2) 取消模型验证按钮，直接选择模型

#### 设计

- 删除模型项里的“验证模型”“验证并添加”按钮。
- 用户点击模型卡片或选择按钮后，直接调用“设置当前模型”逻辑。
- UI 上不再展示“待验证 / 验证中”这种阻塞式状态。
- 模型不可用的问题交给后端 fallback 处理。

#### 关键逻辑调整

原本可能是：

```js
async function onValidateAndSelect(modelId) {
  const ok = await verifyModelAvailability(modelId);
  if (!ok) return showError('模型不可用');
  await setCurrentModel(modelId);
}
```

调整后：

```js
async function onSelectModel(modelId) {
  await setCurrentModel(modelId);
  showToast(`已切换到 ${modelId}`);
}
```

#### 模型卡片点击示意

```html
<button class="model-card" data-model-id="openrouter/qwen3-8b">
  <div class="model-card__main">
    <div class="model-name">Qwen3 8B</div>
    <div class="model-meta">openrouter/qwen3-8b</div>
  </div>
  <span class="model-card__arrow">切换</span>
</button>
```

#### JS 事件绑定示意

```js
document.addEventListener('click', async (e) => {
  const card = e.target.closest('[data-model-id]');
  if (!card) return;
  const modelId = card.dataset.modelId;
  await onSelectModel(modelId);
});
```

#### 需要同步删除的 UI 文案

- “验证模型”
- “验证并添加”
- “模型待确认”
- “先验证再使用”

#### 保留的能力

- 刷新模型列表。
- 切换 Provider 筛选。
- 当前模型展示。
- 手动添加模型时，保留最小必要输入，不再要求先验证。

---

### 3) 缩小模型字体和卡片密度

#### 设计

- 模型标题从大号标题改成中小号文本。
- 模型 ID、标签、状态全部降一档字号。
- 减少 padding 和行高，提升单屏密度。

#### 建议样式

```css
.model-list {
  display: grid;
  gap: 8px;
}

.model-card {
  padding: 10px 12px;
  min-height: 56px;
  font-size: 12px;
}

.model-name {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
}

.model-meta,
.model-status,
.model-badge {
  font-size: 11px;
  line-height: 1.1;
}
```

#### 视觉原则

- 让“名称”保留主要可读性。
- “ID/状态”做辅助信息，避免占用太多视觉重量。
- 通过缩小间距而不是隐藏信息，降低误操作风险。

---

## 具体实施步骤

### Step 1: 重构 Provider 配置区 DOM

1. 找到 `public/index.html` 中 Provider 配置区的静态结构。
2. 抽出统一的卡片容器。
3. 用现有 Provider 数据循环渲染卡片。
4. 保持保存、修改、状态展示逻辑不变。

### Step 2: 清理模型验证相关 UI

1. 删除模型列表里的验证按钮。
2. 删除验证流程分支。
3. 将点击模型后的动作统一为“立即切换”。
4. 调整空状态和错误提示文案。

### Step 3: 压缩模型区视觉密度

1. 调小模型名、模型 ID、标签字号。
2. 减小卡片 padding 和按钮高度。
3. 调整网格间距，增加单屏可见数量。
4. 在移动端继续保持可点性，不低于最小触控尺寸。

### Step 4: 回归检查

1. 检查 Provider 卡片在桌面/移动端是否换行正常。
2. 检查点击模型是否直接切换成功。
3. 检查 fallback 是否仍能在后端兜底。
4. 检查页面是否明显减少纵向滚动。

---

## 风险与处理

- **风险 1：用户误选不可用模型**
  - 处理：保留后端 fallback 和清晰失败提示，不在前端做二次验证。

- **风险 2：卡片压缩后可读性下降**
  - 处理：只缩小次要信息，标题仍保持清晰。

- **风险 3：Provider 卡片过于拥挤**
  - 处理：用 grid 自适应列数，移动端退化为单列。

---

## 验收标准

- Provider 配置区改为卡片布局后，首屏能看到更多配置项。
- 模型列表中不再出现“验证模型”相关按钮或文案。
- 点击模型即完成切换，无需等待验证结果。
- 模型卡片字号和间距更小，滚动长度明显下降。
- fallback 机制仍保持有效，页面不依赖前端验证兜底。

---

## 推荐落地顺序

1. 先改 Provider 卡片布局。
2. 再删模型验证交互。
3. 最后统一压缩模型字体与间距。

这样能先解决最明显的滚动问题，再做交互简化，风险最低。
