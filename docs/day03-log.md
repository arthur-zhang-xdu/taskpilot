# TaskPilot Day 3 工作日志

日期：2026-10-31（Asia/Shanghai）。Day 3 为开发阶段编号。

## 当前进度

已核对现有 JSONL 样例和生成器，完成下述数据契约设计。本文的校验、约束和导入规则是后续实现要求，尚不代表代码或数据库已实现、已验收。现有 compose.yaml 不在本次修改范围内。

## 故障数据契约 v1

来源：`data/incidents/sample_incidents.jsonl`，生成器为 `scripts/generate_incidents.py`。输入采用 UTF-8 JSONL，每个非空行为一个 JSON 对象；忽略空行，错误报告保留原始物理行号。不修改源文件来修复导入错误。

### 字段与数据库映射

| 字段 | 输入要求 | PostgreSQL 映射与约束 | 业务含义 |
| --- | --- | --- | --- |
| incident_id | 必填字符串，去除首尾空白后非空 | TEXT，PRIMARY KEY | 故障唯一标识；当前 inc_0001 等格式只是样本格式，不强制限制 |
| is_synthetic | 必填严格布尔值；当前模拟数据导入入口要求为 true | BOOLEAN，NOT NULL | 标记合成记录，不能丢弃或将其描述为真实事故 |
| service | 必填字符串，去除首尾空白后非空，大小写敏感 | TEXT，NOT NULL，非空检查 | 服务名，精确匹配；不限制为现有三个服务 |
| occurred_at | 必填 ISO 8601 字符串，必须包含有效 UTC 偏移或 Z | TIMESTAMP WITH TIME ZONE，NOT NULL | 故障发生时刻，应用转换为 UTC |
| error_type | 必填字符串，去除首尾空白后非空，大小写敏感 | TEXT，NOT NULL，非空检查 | 错误类别，不限制为样本现有的五类 |
| severity | 必填字符串，去除首尾空白后仅允许 P1、P2、P3 | TEXT，NOT NULL，CHECK | 当前合成数据等级，不自动修正大小写或猜测等级 |
| message | 必填字符串，去除首尾空白后非空 | TEXT，NOT NULL，非空检查 | 模拟错误描述 |
| resolution | 可省略、null 或字符串；字符串去除首尾空白，空串统一为 null | TEXT，可空 | 模拟处理建议，不表示已执行，也不是已确认根因 |

输入模型拒绝未知字段，避免拼写错误被静默忽略；新增字段时显式更新契约。字符串字段不自动接收数字或布尔值，不更改字符串内部空白。归一化只在内存和入库数据上进行。

数据库主键同时保证唯一和非空。非空字符串检查应拒绝纯空白内容；输入层提供具体字段错误，数据库约束防止绕过输入层写入非法值。当前仅有合成导入入口，未来接入真实数据前须明确来源规则，不能给缺失的 is_synthetic 默认填 false。

### 时间与查询语义

- 拒绝无时区时间，不根据服务器时区猜测。
- 同一时刻的不同偏移表示先转为 UTC，再存储、比较及判重。例如 `2026-10-01T08:00:00+08:00` 等于 `2026-10-01T00:00:00Z`。
- PostgreSQL 带时区时间戳保存时刻，不保留原始时区名称或原始文本；连接会话使用 UTC，展示时可转换为 Asia/Shanghai。
- 查询采用 `[start_time, end_time)`：包含起点，排除终点；两端必须带时区，且起点严格早于终点。服务参数执行相同的首尾空白处理后精确匹配。
- 不把当前样本时间范围写成通用模型限制。样本固定种子 42，覆盖 `[2026-10-01T00:00:00+08:00, 2026-11-01T00:00:00+08:00)`；验证使用固定日期，不依赖运行时的“现在”。

### 重复导入与事务

1. 先读取并校验全部记录，再开始写入；解析或校验失败时不写入任何记录。报告行号、字段和非敏感错误摘要。
2. 按上述规则得到规范化的全部八个字段，缺失的 resolution 视为 null。内容一致指字段值一致，不比较原始 JSON 文本、键顺序或时区字符串。
3. 单个文件内部：同 ID、同内容只保留一条待导入记录，其余计为跳过；同 ID、不同内容则整批失败，报告相关行号。
4. 与数据库比较：同 ID、同内容跳过；同 ID、不同内容报冲突，整批失败，不静默覆盖旧记录。
5. 所有新增记录放入一个事务；写入异常时全部回滚。唯一约束处理并发竞争，若发生唯一冲突则回滚并报错，不将其当作已成功跳过。
6. 成功输出读取数、新增数、跳过数，满足“读取数 = 新增数 + 跳过数”；读取数为非空输入记录数。失败返回非零退出码，新增提交数为 0，不报告成功摘要。

此方案针对当前 100 条数据和低并发场景，允许先完整校验、再读取已有 ID 比较，不扩展为流式或高并发导入平台。

### 最小查询与验收基准

- 数据库按服务与时间过滤，计算总数，并按 error_type 分组计数。
- 排序为数量降序、类别名升序；Top K 必须为正整数，类别不足时返回实际数量。
- 空结果为总数 0、空列表；若输出百分比，分母为过滤后的总数，保留两位小数。
- 初始索引使用 `(service, occurred_at)`，对应服务等值和时间范围过滤；100 条样本不能用于证明性能收益。
- 固定实际样本基准：payment-service，`[2026-10-01T00:00:00+08:00, 2026-10-31T00:00:00+08:00)`，Day 1 已记录总数 49，前三类为 connection_timeout=16、database_connection_error=11、upstream_http_5xx=11。本次未重新执行统计，后续用于数据库交叉核对。
- 独立手写样本基准沿用 Day 1：总数 5，a=2、b=2、c=1。数据库测试还需覆盖等价时区、起终点、空结果、重复导入、冲突与整批回滚。

## 后续待执行

- 检查 PostgreSQL 环境并验证连接。
- 实现输入模型、ORM、会话管理和 Alembic 迁移。
- 实现导入、数据库查询及上述验收验证。
- 更新依赖、README 和实际执行记录；未运行的检查不得标记通过。

日常停止、恢复可以使用：
sudo docker compose --env-file .env stop postgres
sudo docker compose --env-file .env start postgres
## 第四步实际完成记录（2026-10-31）

- 已复用现有 Compose 与本地凭据配置，未修改 compose.yaml；数据库实测为 PostgreSQL 17.11。
- 新增 IncidentInput：严格布尔合成标记、文本归一化、等级校验、未知字段拒绝、带时区时间转换为 UTC。现有 100 条输入全部校验通过。
- 新增 SQLAlchemy Incident、集中 Engine/Session 工厂与事务上下文。模块导入不建立数据库连接；原健康接口未改动。
- 新增 Alembic 首个迁移 `0001_create_incidents`：八列、主键、五个 CHECK 约束和服务时间联合索引。迁移独立定义结构，不依赖动态 ORM 元数据生成历史表。
- 开发库执行前检查为空，已执行 `python -m alembic upgrade head`；current 为 `0001_create_incidents (head)`，check 无模型差异。
- 隔离验证通过随机命名的独立测试库进行，完成后仅删除该测试库。验证脚本保留为 `python -m scripts.verify_db_schema`，需创建数据库权限。
- 已验证：迁移与 ORM 一致、主键/等级/空白文本/非空约束、UTC 时间往返、先写入合法数据再触发约束异常后的整笔回滚、隔离库迁移 downgrade/upgrade。
- 依赖实测：SQLAlchemy 2.0.55、Alembic 1.20.1、psycopg/psycopg-binary 3.3.6；新增间接依赖均记录于 requirements.lock。
- `python -m pytest -q`：26 passed，5 subtests passed；原有 Starlette TestClient 弃用提示仍存在。
- `python -m pip check`：无依赖冲突；`git diff --check` 通过。
- 第五步导入命令、重复 ID 策略的执行实现、业务查询聚合及对应验收尚未完成。开发库当前只创建结构，未导入 100 条业务样本。

上述“后续待执行”为初始计划，以本节实际结果更新第四步状态；数据契约和后续导入规则继续有效。


## 第五步实际完成记录（2026-10-31）

- 新增 `app/db/import_incidents.py` 与 `scripts/import_incidents.py`，命令为
  `python -m scripts.import_incidents --input data/incidents/sample_incidents.jsonl`。
- 文件在建立数据库连接前完整校验，忽略空行且保留物理行号；错误仅报告字段/行号摘要，不回显输入或凭据。
- 文件内及库内相同 ID：全部八个归一化字段相同则跳过，不同则失败。比较覆盖等价时区、首尾空白和空 resolution。成功读取数等于新增加跳过数。
- 数据库比较与新增使用单事务；成功提交后才输出统计。约束异常回滚，失败返回非零退出码；不覆盖已有记录。
- 实际开发库导入前 0 行。首次读取100、新增100、跳过0；第二次读取100、新增0、跳过100；最终总行数100。
- 已逐条核对全部八个字段与规范化源数据一致；源文件 SHA256 保持
  `5949b571ec7576ed50f35076b2cc44121e2317b0a31054edcdfefe571f420f2d`。
- 新增离线校验测试和显式启用的 PostgreSQL 测试。独立测试库中验证首次/重复导入、规范化后文件内/库内判重、文件内冲突、库内冲突、混入非法记录、空文件、CLI 成功统计及失败退出码和敏感内容不回显。
- 通过 before_flush 注入唯一约束竞争：事务内先实际写入一行，随后 ORM 写入触发唯一冲突，验证整体回滚后0行。此为确定性故障注入，不声称做过并发压力测试。
- 测试仅创建并删除自身随机命名的隔离数据库，未对开发库清理或回退迁移。
- 配置补充 Alembic `path_separator=os`，消除新增的路径分隔弃用提示。
- 下一步：实现第六步数据库按服务、时间范围查询与错误类型聚合；本次未实现该业务接口。
- 最终执行 `RUN_POSTGRES_IMPORT_TESTS=1 python -m pytest -q`：38 passed，5 subtests passed，仅保留原有 Starlette 弃用提示；`python -m pip check` 无依赖冲突；`git diff --check` 通过。


## 第六步实际完成记录（2026-10-31）

- 新增 `app/db/repository.py`：按服务和带时区时间范围查询明细，及数据库分组统计函数；新增命令 `python -m scripts.analyze_db_incidents`。
- 服务去首尾空白后精确匹配，时间归一化为UTC，执行左闭右开过滤，拒绝非法/无时区时间、逆序区间、空服务和非正整数Top K。
- 聚合使用一条参数化 SQL：GROUP BY + COUNT + SUM(COUNT(*)) OVER () + 排序 + LIMIT。总数在截断前计算，避免Top K改变百分比分母，并保证同语句快照。
- 计数降序、类别按C排序规则升序，明细按时间和ID排序；空结果总数0、空列表。当前明细面向小数据量，无分页；未新增HTTP API。
- 独立测试复用Day1手写8条样本，手算总数5、a=2/b=2/c=1。覆盖起终点、其他服务排除、并列排序、Top1百分比仍40%、Top K超过类别数、空服务匹配/空时间段结果、等价UTC范围与起点记录、相同时间明细排序、SQL注入文本作为普通参数。
- 隔离库导入实际100条数据后与Day1离线统计交叉核对，CLI结果也一致。
- 开发库实际只读查询 payment-service，区间 `[2026-10-01T00:00:00+08:00,2026-10-31T00:00:00+08:00)`：总数49，connection_timeout=16(32.65%)，database_connection_error=11(22.45%)，upstream_http_5xx=11(22.45%)。
- 最终 `RUN_POSTGRES_IMPORT_TESTS=1 python -m pytest -q`：54 passed，5 subtests passed；仅原有Starlette弃用提示。pip check无依赖冲突，git diff --check通过。
- 测试写入仅发生在自动创建的随机临时数据库中，结束后删除自身测试库；本次开发库只执行查询，未清理数据或重启服务。
- Day3尚需按完整清单收尾：如需重启服务验证持久性应单独执行；面试学习笔记等个人任务未标记完成。

## 第七步验收与回归记录（2026-10-31）

本步复用已有必要测试，不重复增加等价用例，不修改业务实现。

| 检查 | 实际命令或方式 | 结果 |
| --- | --- | --- |
| 默认离线回归 | `python -m pytest -q` | 48 passed，6 skipped，5 subtests passed；6项为默认显式跳过的PostgreSQL集成测试 |
| PostgreSQL集成 | `RUN_POSTGRES_IMPORT_TESTS=1 python -m pytest -q tests/test_import_postgres.py` | 6 passed，使用自行创建的随机隔离库 |
| Day1独立基准 | `python -m unittest discover -s tests -v` | 5项通过 |
| 迁移与约束 | `python -m scripts.verify_db_schema` | 隔离库迁移升降级、模型一致性、约束、UTC往返、事务回滚通过 |
| 依赖检查 | `python -m pip check` | 无依赖冲突 |
| 开发库迁移 | `python -m alembic current` / `python -m alembic check` | 0001_create_incidents (head)，无模型差异 |
| 格式检查 | `git diff --check` | 通过 |

覆盖证据：

- 重复导入不新增；同ID不同内容冲突、文件内冲突、合法数据混入非法数据均不留下部分新增。
- before_flush确定性注入唯一约束冲突，事务内先实际写入一行，异常后数据库计数0，验证真正回滚。
- 等价时区、起点包含/终点排除、其他服务排除、并列排序、空结果、Top K截断不改变百分比分母均通过手写样本验证。
- Day2配置与健康检查包含在离线回归中；禁止socket连接的测试下，/health/live、文档和OpenAPI正常，无需真实模型Key或数据库连接。
- 从临时工作目录执行生成器CLI，输出指定到临时目录，与现有JSONL逐字节相等；未覆盖源数据。
- 开发库仅执行只读核对：仍为100行，逐条全部八字段与规范化源数据一致。源文件SHA256仍为 `5949b571ec7576ed50f35076b2cc44121e2317b0a31054edcdfefe571f420f2d`。
- 数据库支付服务30天统计与原Python统计交叉一致：总数49，前三类16/11/11。

执行使用既有taskpilot Conda环境。测试清理仅针对本次脚本创建的随机数据库；未对开发库删表、清库、回退迁移或重启。没有调用真实模型API。

当前仅保留已有Starlette TestClient弃用提示，不影响通过。本步未验证服务重启后的持久性；若要完成该独立验收项，后续需保留数据卷重启数据库再核对。第七步边界、事务与回归验证已完成；第八步学习笔记及Day3整体收尾仍需单独处理。
