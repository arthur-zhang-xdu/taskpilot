# TaskPilot

可评测的研发故障分析 Agent。当前具备模拟故障生成、离线与 PostgreSQL 查询统计、配置管理、FastAPI 存活检查及只读统计接口；Agent 和知识检索尚未实现。

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

## Day 3 数据模型与迁移

已实现输入模型 `app/schemas/incident.py`、故障表 `app/db/models.py` 和显式会话管理
`app/db/session.py`。输入严格保留八个字段，拒绝未知字段与无时区时间，统一转换为 UTC。
当前输入入口只接受 `is_synthetic=true`；数据库保留布尔标记，不限定未来数据来源。
数据库约束覆盖主键、非空、非空白文本和 P1/P2/P3 等级，索引为 `(service, occurred_at)`。

数据库配置复用 Compose 的 `POSTGRES_USER`、`POSTGRES_DB`、`POSTGRES_PASSWORD`，
主机默认 `127.0.0.1`，端口默认 `5432`。也可设置优先级更高的 `DATABASE_URL`，
驱动必须为 `postgresql+psycopg`。凭据通过 Settings 读取，不写入 Alembic 配置。
不要覆盖已有 `.env`；按 `.env.example` 补充缺少的变量。

数据库启动后，在项目根目录、taskpilot 环境中显式执行：

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

应用启动不会自动连接数据库或修改表结构。业务操作使用
`create_session_factory(engine)` 与 `with session_scope(factory) as session:`；
成功提交，异常回滚，结束关闭会话。Engine 由调用方复用并在退出时 dispose。

验证迁移、约束、UTC 和事务回滚：

```bash
python -m pytest -q
python -m scripts.verify_db_schema
```

后一个命令需要当前数据库用户拥有创建数据库权限，并能连接 `postgres` 管理库。
它创建随机命名的临时数据库，仅在该库执行迁移升降级和测试，最终删除自己创建的库；
不会清空开发库。数据库查询与聚合用法见下文。


## Day 3 JSONL 导入

先启动 PostgreSQL 并执行迁移，然后在项目根目录运行：

```bash
python -m scripts.import_incidents --input data/incidents/sample_incidents.jsonl
```

成功输出 `{"read": 100, "inserted": 100, "skipped": 0}`；相同文件再次导入输出
`{"read": 100, "inserted": 0, "skipped": 100}`。`read` 为非空行数，始终等于
`inserted + skipped`。空文件返回三个 0，不写入数据。

先完整校验文件，再在一个事务内比较和写入。文件内部及库内的相同 ID 若八个字段
归一化后相同则跳过；内容不同则报错，整批不提交，不覆盖旧记录。
比较包含 UTC 时间归一化、文本首尾去空白及缺省 resolution=null。
非法数据报告物理行号和字段，内容冲突报告相关行号，错误不回显原始记录或数据库凭据。
文件、配置、连接、约束等错误返回非零退出码；数据库约束异常回滚整个事务。
数据库操作失败时不要依据失败输出认定导入成功，连接中断后可恢复连接并安全重试。
本入口针对小批量、低并发场景，完整数据会加载到内存。

离线测试默认不连接 PostgreSQL。显式运行隔离数据库集成测试：

```bash
RUN_POSTGRES_IMPORT_TESTS=1 python -m pytest -q
```

集成测试需要 `.env` 中的数据库用户具有创建数据库权限；它仅在随机命名的独立库中
执行迁移与写入测试，最后删除自己创建的测试库，不清理开发库。


## Day 3 数据库查询与聚合

在项目根目录、taskpilot 环境中执行：

```bash
python -m scripts.analyze_db_incidents \
  --service payment-service \
  --start '2026-10-01T00:00:00+08:00' \
  --end '2026-10-31T00:00:00+08:00' \
  --top-k 3
```

当前样本预期总数49，前三类数量为16、11、11，百分比32.65%、22.45%、22.45%。
服务名去首尾空白后精确匹配；时间必须带时区，输出统一为 UTC；区间为 `[start,end)`，
起点必须早于终点；top-k 为正整数。无匹配时总数为0、分类列表为空。

`app/db/repository.py` 提供 `query_incidents(factory, service, start_time, end_time)`
和 `summarize_incidents(factory, service, start_time, end_time, top_k=3)`。
明细返回八个字段，按时间、ID升序排列；当前仅用于小规模数据验证，尚未提供分页。
聚合在数据库中 GROUP BY，数量降序、类型名按 C 排序规则升序，LIMIT 返回 Top K。
窗口函数在 LIMIT 前求过滤后总数，使总数与分类处于同一语句快照；百分比分母为全部过滤记录。
查询值通过参数绑定传入，不开放任意 SQL。统计命令不读取 JSONL、不请求模型、不写入故障数据。
输入或数据库失败返回非零退出码，错误摘要不回显连接凭据。

验证仍使用 `RUN_POSTGRES_IMPORT_TESTS=1 python -m pytest -q`，其中也包含查询聚合的隔离库测试。

## Day 4 只读统计接口

`GET /incidents/summary` 复用现有数据库聚合，不新增表、不自动迁移或导入数据。
按上文启动应用后，可使用：

```bash
curl --get 'http://127.0.0.1:8000/incidents/summary' \
  --data-urlencode 'service=payment-service' \
  --data-urlencode 'start_time=2026-10-01T00:00:00+08:00' \
  --data-urlencode 'end_time=2026-10-31T00:00:00+08:00' \
  --data-urlencode 'top_k=3'
```

前三项必填，`top_k` 默认为 3，接受正整数文本，不设置额外上限。
服务名去首尾空白后精确匹配，时间必须为带时区的 ISO 8601 字符串，
区间为左闭右开且起点早于终点。使用 URL 编码避免 `+08:00` 的加号被解释为空格。

共享输入模型为 `app/schemas/summary.py` 中的 `SummaryQuery`：时间归一化为 UTC
ISO 字符串，可供后续工具复用；直接使用 Python 模型时 `top_k` 必须为整数。
响应模型 `SummaryResponse` 保留 repository 字段：`service`、`start_inclusive`、
`end_exclusive`、`total_incidents`、`top_k`、`top_errors`。
每个分类包含 `error_type`、`count`、`percentage`，百分比分母为全部匹配故障数，
不是 Top K 数量之和；时间输出为 UTC，JSON 可使用 `Z` 表示 UTC。
`data_source="synthetic_incidents"` 说明当前数据集来自合成故障，
不是新增来源过滤条件；未来接入真实数据时需同步调整该契约。

非法参数返回 422；无匹配返回 200、`total_incidents=0` 和 `top_errors=[]`。
缺少数据库配置或数据库连接运行不可用返回 503，响应只包含通用说明，
不回显凭据、SQL 或异常详情；编程错误不统一转换为 503。

同步路由在工作线程执行数据库操作。每个应用延迟创建并复用一个 Engine 和
Session 工厂，repository 在每次操作结束时关闭 Session，应用退出时释放 Engine。
健康检查、文档与 OpenAPI 不初始化数据库连接池。测试可覆盖
`app.api.incidents.get_session_factory` 依赖以替换数据库访问。

Day 4 验证结果（2026-11-02）：

- `python -m pytest -q`：62 passed、7 skipped、5 subtests passed。
- `RUN_POSTGRES_IMPORT_TESTS=1 python -m pytest -q tests/test_import_postgres.py tests/test_summary_postgres.py`：7 passed，在自动创建的隔离库中验证。
- `python -m unittest discover -s tests -v`：5 项通过。
- 真实 Uvicorn HTTP 与开发库只读 CLI 对照：总数 49，前三类 16/11/11，百分比 32.65%/22.45%/22.45%。
- 真实 HTTP 空结果 200、非法与缺失参数 422；独立不可用连接返回安全的 503，健康、文档及 OpenAPI 仍为 200。
- `python -m pip check`、`git diff --check` 通过。仍有已有的 Starlette TestClient 弃用提示。

默认跳过的 7 项均为显式启用的 PostgreSQL 集成测试，已通过上述独立命令运行。
完整实施记录、验证范围及 Day 5 接续见 `docs/day04-log.md`。
