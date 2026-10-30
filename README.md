# TaskPilot

可评测的研发故障分析 Agent。当前具备模拟故障生成、离线查询统计、配置管理及 FastAPI 存活检查；Agent、数据库和知识检索尚未实现。

## 环境与安装

支持 Python 3.11–3.14，实际验证环境为 Ubuntu / Python 3.11.18。继续使用已有 Conda 环境：

```bash
cd /home/ubuntu/taskpilot
conda activate taskpilot
python -m pip install -r requirements.lock
python -m pip install --no-build-isolation -e '.[test]'
```

`pyproject.toml` 声明项目依赖，`requirements.lock` 记录本次验证的直接和间接依赖精确版本（包含测试依赖与构建工具）。新增或更新依赖后需要重新验证并更新版本记录。其他 Python 版本尚未实际验证。

也可以先用 `python3.11 -m venv .venv` 创建干净环境，再执行 `source .venv/bin/activate` 和上述安装命令。

## 配置

```bash
cp .env.example .env
```

`.env` 固定读取项目根目录下的文件，与启动时的工作目录无关；真实密钥只保存在本地，不提交 Git。

优先级：显式传入 `Settings(...)` 的参数 > 环境变量 > `.env` > 默认值。测试可通过 `Settings(_env_file=None)` 禁用文件读取。

| 变量 | 默认值 / 规则 |
| --- | --- |
| APP_NAME | TaskPilot，非空 |
| APP_ENV | development，可选 development/test/production |
| LOG_LEVEL | INFO，可选 DEBUG/INFO/WARNING/ERROR/CRITICAL；当前作为配置保存 |
| LLM_API_KEY | 空，使用 SecretStr 保护 |
| LLM_BASE_URL | 空，示例文件沿用 Day 1 火山方舟地址 |
| LLM_MODEL | 空，示例文件沿用 Day 1 模型 |
| LLM_TIMEOUT_SECONDS | 30，必须为有限正数 |

基础服务无需模型 Key。当前 Web 服务不调用模型；模型请求前的必要参数检查仍由 Day 1 脚本负责。不要打印整个配置对象或异常的结构化输入。

## 启动和访问

在项目根目录运行：

```bash
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

另一个终端验证：

```bash
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/openapi.json
```

默认健康响应：`{"status":"ok","service":"TaskPilot"}`，HTTP 200。它只表示应用存活，不访问外部模型或数据库。不匹配的路由返回 404。

浏览器接口文档位于 `/docs`。通过本地 SSH 转发访问服务器：

```bash
ssh -N -L 8000:127.0.0.1:8000 ubuntu@你的服务器地址
```

然后打开本地 `http://127.0.0.1:8000/docs`。开发需要时可给启动命令添加 `--reload`。

## 测试

```bash
python -m pytest -q
python -m unittest discover -s tests -v
python -m pip check
```

新增测试隔离真实 `.env` 和应用环境变量，不请求模型。unittest 命令用于单独回归 Day 1 的 5 项测试。

## Day 1 入口

生成模拟数据（会覆盖默认数据文件）：

```bash
python scripts/generate_incidents.py
```

统计指定服务的 30 天故障，时间区间为左闭右开：

```bash
python scripts/analyze_incidents.py --service payment-service --start '2026-10-01T00:00:00+08:00' --end '2026-10-31T00:00:00+08:00'
```

模型验证：`python scripts/check_llm.py --timeout 120`。该脚本仍直接读取同一终端 export 的 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL`，不会自动加载 `.env`；运行会发起真实模型请求，日常离线验证无需执行。

详细记录见 `docs/day01-log.md` 和 `docs/day02-log.md`。
