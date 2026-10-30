# TaskPilot Day 2 工作日志

日期：2026-10-30（Asia/Shanghai）。实际投入时长未记录。
项目：`/home/ubuntu/taskpilot`；继续使用 Conda taskpilot / Python 3.11.18。

## 完成内容

- 新增 `.gitignore`，忽略 `.env`、缓存、虚拟环境和构建产物；保留 `.env.example`。5 个已跟踪的 `.pyc` 从 Git 索引移除，保留本地文件。
- 新增 `pyproject.toml`，声明项目元数据、应用包发现、运行和测试依赖；新增 `requirements.lock`，记录实测依赖和构建工具精确版本。
- 新增 README，记录安装、配置、启动、SSH 转发、测试及 Day 1 脚本入口。
- 新增 `app/main.py` 应用工厂、`app/core/config.py` 类型化配置和 `app/api/health.py` 存活检查。
- 新增 `.env.example`，沿用 Day 1 模型地址及名称，不含真实密钥。
- 新增配置与接口测试。现有 Day 1 脚本、数据和测试未重写。

## 设计决定

- 显式 Settings 参数 > 环境变量 > 项目根目录 `.env` > 默认值。测试隔离开发环境变量和真实配置文件。
- Key 使用 SecretStr；校验错误文本隐藏输入。不提供配置转储接口。超时要求有限正数，日志级别和应用环境使用允许集合。
- 基础启动无需模型凭据，健康接口不访问网络。Day 1 模型脚本仍读取终端环境变量，不自动读取 `.env`。
- `LOG_LEVEL` 当前仅作为配置保存，尚未用于重配 Uvicorn 日志。
- 使用工厂入口，不通过修改 sys.path 解决导入。

## 实际验证

项目环境执行：

```bash
python -m pytest -q
python -B -m unittest discover -s tests -v
python -m pip check
```

结果：pytest 15 passed（另有 5 subtests passed）；Day 1 unittest 5 项通过；无依赖冲突。
测试覆盖配置优先级、非法超时和日志级别、秘密值屏蔽、无 Key 启动、禁止外网连接的健康检查、配置注入、404 和文档入口。

干净环境位于 `/tmp/taskpilot-day2-verify`，由项目 Python 创建。依照 README 执行：

```bash
python -m pip install -r requirements.lock
python -m pip install --no-build-isolation -e '.[test]'
python -m pytest -q
python -m pip check
```

安装成功，15 项测试通过，无依赖冲突。验证过程发现构建工具也需要精确记录，已补入 setuptools 和 wheel。仅实际验证了 Python 3.11.18。

真实启动命令：

```bash
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

在干净环境启动，移除应用相关环境变量后验证：

- `/health/live`：HTTP 200，`{"status":"ok","service":"TaskPilot"}`。
- `/docs`：HTTP 200。
- `/openapi.json`：HTTP 200。

验证后已终止该服务进程。没有执行真实模型调用。
`git check-ignore` 确认 `.env`、`.env.local` 和 Python 缓存被忽略；`git diff --check` 通过。

## 限制与后续

- 当前 Starlette 对 TestClient 使用 HTTPX 发出一条弃用提示，测试正常通过。后续升级测试客户端时再处理，不屏蔽该提示。
- 未审计 Git 全部历史中的密钥，不能宣称已完成历史密钥安全审计。
- 未提交或推送代码；缓存的取消跟踪操作已暂存，新增文件尚未暂存。
- 尚未完成当天独立的面试基础练习；不据此宣称 Day 2 全部个人学习任务完成。
- Day 3 可基于既有数据推进数据模型和数据库方案，不重复生成同样的数据。
