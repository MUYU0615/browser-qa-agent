# Browser QA Agent

一个基于 **LangGraph + Playwright** 的浏览器自动化 QA Agent。它可以打开目标网页，分析页面结构，调用 DeepSeek 生成安全的测试步骤，用 Playwright 执行浏览器操作，收集截图、控制台错误、网络错误，并生成 Markdown 测试报告。

这个项目的重点不是 RAG，而是展示 LangGraph 在真实 agent 工作流里的价值：状态流转、条件分支、失败重试、工具调用、过程可观测和结果持久化。

## 核心功能

- LangGraph 工作流编排：
  `page_analyzer -> test_planner -> browser_executor -> observation_analyzer -> bug_classifier -> retry_planner? -> reporter`
- DeepSeek OpenAI-compatible 调用，默认模型为 `deepseek-v4-pro`
- 没有 API key 时提供 deterministic fallback，方便本地演示和测试
- Playwright 自动化浏览器操作，支持截图、console error、network error 捕获
- FastAPI 后端，提供创建 run、查询状态、读取报告、访问截图等接口
- React Dashboard，展示 URL 输入、图执行状态、事件日志、问题列表、截图和报告
- 本地文件存储，每次运行结果保存到 `runs/<run_id>/`

## 项目结构

```text
browser-qa-agent/
  backend/
    app/
      graph/          # LangGraph 状态、节点和 workflow
      services/       # 浏览器、LLM、运行记录存储
      prompts/        # Planner/Judge 提示词
      main.py         # FastAPI 入口
    tests/            # 后端单元测试
    requirements.txt
    .env.example
  frontend/
    src/
      components/     # Dashboard 组件
      api.ts          # 后端 API 客户端
      App.tsx
    package.json
  runs/               # QA run 输出目录
  README.md
```

## 环境要求

- Python 3.11+，当前项目已在 Python 3.14 下验证
- Node.js 20+
- npm 10+
- DeepSeek API key

建议先轮换你曾经在聊天里暴露过的 key，再把新 key 填入本地 `.env`。

## 后端安装

```powershell
cd D:\MUYU\browser-qa-agent
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

安装 Playwright Chromium。为了避免写入用户目录，建议把浏览器二进制放到项目内：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH="D:\MUYU\browser-qa-agent\backend\.playwright-browsers"
backend\.venv\Scripts\python.exe -m playwright install chromium
```

创建后端环境变量文件：

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
cd D:\MUYU\browser-qa-agent
$env:PLAYWRIGHT_BROWSERS_PATH="D:\MUYU\browser-qa-agent\backend\.playwright-browsers"
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health
```

## 前端安装

```powershell
cd D:\MUYU\browser-qa-agent\frontend
npm install
npm run dev -- --host 127.0.0.1
```

打开：

```text
http://127.0.0.1:5173
```

如果 npm 缓存目录权限有问题，项目已经提供 `frontend/.npmrc`，会把缓存写到 `frontend/.npm-cache`。

## 使用方式

1. 启动后端和前端。
2. 在 Dashboard 输入目标 URL，例如 `http://localhost:3000`。
3. 点击 `Start QA Run`。
4. 页面会展示 LangGraph 当前节点、运行日志、截图、问题列表和最终报告。
5. 每次运行的原始结果会保存在 `runs/<run_id>/`。

## 后端 API

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

## 测试和构建

后端测试：

```powershell
cd D:\MUYU\browser-qa-agent
backend\.venv\Scripts\python.exe -m pytest backend\tests -v
```

前端构建：

```powershell
cd D:\MUYU\browser-qa-agent\frontend
npm run build
```

完整浏览器烟测可以通过 Dashboard 手动创建一次 run，也可以直接调用 FastAPI 创建 run 后轮询状态。

## 安全边界

第一版默认跳过高风险动作，例如支付、下单、删除账号、退订、不可逆提交等。当前版本适合测试本地开发环境、演示站点或 staging 页面，不建议直接对生产账号执行自动化操作。

## 简历描述参考

```text
Built a LangGraph-based Browser QA Agent that plans, executes, and evaluates browser workflows using Playwright. The system supports graph-based task orchestration, conditional retries, browser tool calling, screenshot/error collection, and automated bug report generation.
```

中文描述：

```text
开发 Browser QA Agent，基于 LangGraph 编排网页测试工作流，使用 Playwright 执行浏览器操作，支持页面分析、测试步骤规划、条件重试、错误分类、截图采集和自动化 QA 报告生成。
```
