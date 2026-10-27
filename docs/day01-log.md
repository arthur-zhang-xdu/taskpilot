# TaskPilot Day 1 工作日志

日期：2026-10-27（Asia/Shanghai）。实际投入时长未记录。

## 当前结论

Day 1 四项核心证据已具备：服务器环境检查记录、真实模型调用成功记录、可复现的 100 条合成故障、经独立手写样本验证的 Python 统计。尚未完成全部验收清单；Embedding 验证、密钥与 Git 忽略规则检查等事项见文末。

证据来源：环境、文件摘要和项目 Python 环境下的测试由助手实际检查；真实模型成功调用依据用户在当前对话提供的完整结果，本次整理日志没有再次请求模型。

## 环境检查

| 项目 | 实测结果 |
|---|---|
| 项目目录 / Git 仓库根目录 | `/home/ubuntu/taskpilot` |
| 当前用户 | `ubuntu` |
| 操作系统 | Ubuntu 26.04.1 LTS |
| 架构 / 可用逻辑 CPU 数 | x86_64 / 2 |
| 内存 | 总计 3.6 GiB，检查时可用约 1.6 GiB |
| Swap | 总计 2.0 GiB |
| 项目所在磁盘 | 总计 88 GiB，检查时可用约 74 GiB |
| Git | 2.53.0 |
| Conda | 26.9.4 |
| 项目 Python | 3.11.18 |
| 项目 pip | 26.2.2 |
| 项目解释器路径 | `/home/ubuntu/miniconda3/envs/taskpilot/bin/python` |
| 助手默认终端 Python | 系统 Python 3.14.4；不是项目环境 |
| Docker / Compose | 当前执行环境找不到 docker 命令，未验证运行权限；不阻塞 Day 1 |

用户已通过 SSH 终端运行命令；SSH 服务配置未审计。助手执行工具的默认沙箱出现 `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`，随后按权限流程执行检查。这不代表服务器自身网络配置有问题。

开发时使用：

```bash
cd /home/ubuntu/taskpilot
conda activate taskpilot
python --version
```

当天三个脚本和测试仅使用 Python 标准库，没有新增第三方运行依赖。尚未导出 Conda 环境或完整依赖清单。

日志整理前，`git status --short` 显示 `data/`、`scripts/`、`tests/` 为未跟踪文件；本次未提交或推送。

## 真实模型 API 验证

最终供应商：火山引擎 / 火山方舟。

- 基础地址：`https://ark.cn-beijing.volces.com/api/v3`
- 模型：`doubao-seed-2-0-lite-260428`
- 凭据读取方式：环境变量 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。
- Key 由用户在终端隐藏输入；本日志不保存密钥。终端环境变量不会随新 SSH 会话自动恢复。
- 脚本：`scripts/check_llm.py`；关闭思考模式、最大输出 64 Token、不自动重试。

运行命令（先在同一终端配置上述变量）：

```bash
python scripts/check_llm.py --timeout 120
```

用户提供的真实运行结果：

```json
{
  "success": true,
  "model": "doubao-seed-2-0-lite-260428",
  "elapsed_seconds": 2.529,
  "reply": "TaskPilot API 测试成功",
  "usage": {
    "prompt_tokens": 40,
    "completion_tokens": 7,
    "total_tokens": 47
  }
}
```

此前智谱 GLM-4.7-Flash 出现 30 秒超时，后续 curl 请求返回业务错误码 1305（访问量过大），未获得成功模型回复。一次使用 `YOUR_API_KEY` 示例占位符的请求返回认证错误，不作为真实凭据验证结论。最终切换供应商后成功。

Embedding API 尚未验证，供应商与具体模型待确定；不影响当天数据和统计任务。

## 模拟故障数据

```bash
python scripts/generate_incidents.py
```

- 脚本：`scripts/generate_incidents.py`。
- 数据：`data/incidents/sample_incidents.jsonl`，UTF-8，每行一条 JSON。
- 固定种子：42；100 条记录，ID 唯一，按发生时间和 ID 排序。
- 时间范围：`[2026-10-01T00:00:00+08:00, 2026-11-01T00:00:00+08:00)`。
- 服务数量：payment-service 50、order-service 30、user-service 20。
- 错误数量：connection_timeout 35、database_connection_error 25、upstream_http_5xx 20、rate_limit_exceeded 12、invalid_request 8。
- 数量分布由代码预设；种子决定服务、错误配对和时间，不代表真实故障分布。
- 每条包含 `is_synthetic: true`；描述注明模拟，处理建议注明未执行、未验证根因。

SHA-256：

```text
5949b571ec7576ed50f35076b2cc44121e2317b0a31054edcdfefe571f420f2d
```

助手已检查记录数量、唯一 ID、预设分布、带时区的时间边界和模拟标识。在临时目录重复生成并逐字节比较一致，换种子后文件变化，从其他工作目录运行也成功。用户重复运行生成脚本后的摘要与上述 SHA-256 一致。

注意：生成脚本会覆盖指定输出文件。

## 查询与统计验证

```bash
python scripts/analyze_incidents.py \
  --service payment-service \
  --start '2026-10-01T00:00:00+08:00' \
  --end '2026-10-31T00:00:00+08:00'
```

用户执行成功；助手另使用项目 Python 3.11.18 复核，结果一致：

| 错误类型 | 数量 | 占过滤后总数 |
|---|---:|---:|
| connection_timeout | 16 | 32.65% |
| database_connection_error | 11 | 22.45% |
| upstream_http_5xx | 11 | 22.45% |

过滤后总数为 49，Top 3 共 38 条。查询是 30 天，不包含 10 月 31 日；整个 10 月共 31 天，支付服务全月有 50 条。

规则：服务精确匹配，时间采用 `[start, end)`，必须携带时区；数量降序、同数量按错误名称升序；默认 Top K 为 3，类别不足则返回实际数量；百分比分母为全部过滤结果，保留两位小数；空结果返回 0 和空列表；无效输入以非零退出码报告错误。统计由 Python 完成，没有调用 LLM。

统计结果当前输出到终端，没有另存为结果文件。

### 独立小样本

```bash
python -m unittest discover -s tests -v
```

测试文件：`tests/test_incident_analysis.py`。手写 8 条数据，不使用生成器生成基准，不通过被测函数计算预期答案。手算查询结果：5 条，a=2、b=2、c=1，对应 40%、40%、20%。

用户及助手在项目 Python 环境下均验证 5 项测试全部通过，覆盖：

- 服务过滤、起点包含、终点排除、并列排序和百分比。
- Top K 截断后分母不变，类别不足时返回实际数量。
- 空数据和无匹配服务。
- 等价 UTC 时间范围。
- 无效时间、无时区、逆序/相等区间、无效 Top K 和缺失记录字段。

## 已完成、待补与下一步

已完成：隔离 Python 环境、服务器基本资源检查、真实文本 API 调用、可复现数据生成、统计 CLI 与独立样本验证，以及本日志。

尚未确认或未完成：

- 尚未完成 `.gitignore`、仓库及历史的密钥排查；不能据此宣称已完成密钥安全验收。
- 尚未形成 `.env.example`、README 运行说明和环境依赖记录。
- Embedding 模型和可达性待验证。
- Docker 未检测到；当天无需为此安装。
- 实际投入时长和面试基础练习未记录。
- 尚未实现 Agent 工具调用、Trace、知识检索、FastAPI 或报告生成，不作为 Day 1 已有成果。

下一步先补齐忽略规则、环境记录和最小运行文档，再进入 Day 2：将查询统计封装成受限工具，跑通最小模型工具调用循环并记录执行轨迹。模型不执行任意 SQL 或 Shell，不进行真实修复；分析时区分事实、推测和待验证事项。
