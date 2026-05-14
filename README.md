# Browser QA Agent

一个基于 **LangGraph + Playwright + DeepSeek** 的浏览器自动化 QA Agent。

它会打开目标网页，分析可交互组件，让大模型规划符合真实用户行为的测试场景，再由 Playwright 执行浏览器操作，并收集截图、控制台错误、网络错误、执行步骤和 Markdown 报告。

这个项目重点展示的是 Agent 工作流在浏览器 QA 场景里的落地方式：页面观察、场景规划、浏览器执行、动态组件发现、错误分析、报告生成和运行过程可观测。

## 功能特性

- **LangGraph 工作流编排**：将页面分析、测试执行、问题分析、缺陷分类和报告生成拆成清晰节点。
- **大模型场景规划**：调用 DeepSeek 生成测试场景，不再逐个组件孤立点击。
- **真实用户流程测试**：例如登录页会规划成“填写 username + 填写 password + 点击 Login”的完整流程。
- **动态组件发现**：点击 Add Element 后如果出现 Delete，会继续识别并追加测试新组件。
- **Playwright 浏览器自动化**：执行点击、填写、选择、勾选、文本断言和标题断言。
- **错误采集**：自动收集 console error、page error、HTTP 4xx/5xx 网络错误和交互失败。
- **可视化 Dashboard**：前端展示运行状态、LLM 调用、Attempts、截图、问题列表和报告。
- **本地持久化**：每次运行的状态、截图、LLM trace 和报告保存到 `runs/<run_id>/`。
- **无 API Key 降级模式**：没有 DeepSeek key 时也能使用 deterministic fallback 做本地演示和测试。

## 工作流

```text
page_analyzer
  -> component_coverage_executor
  -> observation_analyzer
  -> bug_classifier
  -> reporter
```

核心执行逻辑：

1. `page_analyzer` 使用 Playwright 打开页面并提取可交互元素。
2. `component_coverage_executor` 请求 LLM 将组件编组成测试场景。
3. Playwright 按场景连续执行步骤，并在每次成功交互后重新观察页面。
4. 如果页面出现新组件，会追加到当前场景继续测试。
5. `observation_analyzer` 和 `bug_classifier` 汇总错误与异常。
6. `reporter` 生成 Markdown QA 报告。

## 项目结构

```text
browser-qa-agent/
  backend/
    app/
      graph/          # LangGraph 状态、节点和工作流
      services/       # 浏览器执行、LLM 调用、运行记录存储
      prompts/        # 提示词文件
      main.py         # FastAPI 入口
    tests/            # 后端测试
    requirements.txt
    .env.example
  frontend/
    src/
      components/     # Dashboard 组件
      api.ts          # 后端 API 客户端
      App.tsx
    package.json
  runs/               # 本地运行产物，默认不提交
  README.md
```

## 技术栈

- 后端：Python、FastAPI、LangGraph、Playwright、OpenAI-compatible SDK
- 模型：DeepSeek，默认 `deepseek-v4-pro`
- 前端：React、TypeScript、Vite、Lucide Icons
- 测试：pytest、TypeScript build

## 环境要求

- Python 3.11+
- Node.js 20+
- npm 10+
- DeepSeek API Key，可选；没有 key 也可以使用 fallback 演示

## 后端安装

在项目根目录执行：

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

安装 Playwright Chromium。建议把浏览器二进制安装到项目目录内，避免写入用户全局目录：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH="D:\MUYU\browser-qa-agent\backend\.playwright-browsers"
backend\.venv\Scripts\python.exe -m playwright install chromium
```

创建环境变量文件：

```powershell
Copy-Item backend\.env.example backend\.env
```

编辑 `backend\.env`：

```env
DEEPSEEK_API_KEY=your_deepseek_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
RUNS_DIR=runs
CORS_ORIGINS=http://localhost:5173
PLAYWRIGHT_BROWSERS_PATH=backend/.playwright-browsers
```

启动后端：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH="D:\MUYU\browser-qa-agent\backend\.playwright-browsers"
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health
```

## 前端安装

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

打开：

```text
http://127.0.0.1:5173
```

## 使用方式

1. 启动后端和前端。
2. 在 Dashboard 输入要测试的 URL，例如 `http://localhost:3000`。
3. 点击开始运行。
4. 页面会展示 LangGraph 节点、运行日志、LLM 调用、Attempts、截图、问题列表和报告。
5. 原始运行产物会保存到 `runs/<run_id>/`。

## API

- `GET /api/health`：健康检查
- `POST /api/runs`：创建一次 QA run
- `GET /api/runs`：列出所有 runs
- `GET /api/runs/{run_id}`：查询单次 run 状态
- `GET /api/runs/{run_id}/report`：读取 Markdown 报告
- `/runs/<run_id>/<file>`：访问截图和运行产物

创建 run 示例：

```powershell
$body = @{ url = "http://localhost:3000" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/runs" -Method Post -ContentType "application/json" -Body $body
```

## 测试与构建

后端测试：

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

前端构建：

```powershell
cd frontend
npm run build
```

## 安全边界

当前版本会过滤高风险动作，例如支付、下单、购买、退订、删除账号、关闭账号和脚本注入等。建议优先用于本地开发环境、演示站点或 staging 页面，不建议直接对生产账号执行自动化操作。

## 上传 GitHub 前注意

`.gitignore` 已默认忽略以下内容：

- `backend/.env`
- `backend/.venv/`
- `backend/.playwright-browsers/`
- `frontend/node_modules/`
- `frontend/dist/`
- `runs/*`
- `.mcp.json`

上传前请确认不要提交真实 API Key、运行截图、浏览器二进制和本地缓存。

## 简历描述参考

```text
开发 Browser QA Agent，基于 LangGraph 编排浏览器 QA 工作流，使用 Playwright 执行自动化操作，并接入 DeepSeek 进行测试场景规划与缺陷判断。系统支持页面结构分析、真实用户流程测试、动态组件发现、错误采集、截图留存、LLM 调用追踪和 Markdown QA 报告生成。
```
