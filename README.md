# 一休云自动化测试项目

本仓库是基于 Python 和 pytest 的一休云业务自动化测试项目，主要用于验证一休云服务接口、业务流程和相关系统的集成行为。仓库包含 HTTP API 测试、Bash 机台通信测试、Selenium UI 测试，以及模型训练、标注、样例管理和产品资料等业务模块。

本仓库面向 GitHub 公开分享，源码已做脱敏处理。它不是可直接连接真实环境的开箱即用演示项目。执行集成测试需要使用者自行准备环境配置、账号、测试数据、授权凭证，以及对应的服务或客户端依赖。

## 项目功能

- **业务 API 自动化**：通过封装的 HTTP 客户端访问业务接口，测试登录与 Token、2D/3D 标注、模型训练、产品资料、样例库、仿真和任务管理等功能。
- **Bash 机台通信**：包含 gRPC 设备通信、前置条件验证和推图相关测试。运行这些场景需要匹配的服务地址、设备授权信息、证书和外部测试资源。
- **Web UI 自动化**：使用 Selenium 验证 Bash 相关页面操作。需要可访问的 Web 环境和本机浏览器及驱动。
- **测试调度与依赖管理**：提供按顺序或并行组织测试任务的入口，可根据任务依赖配置补全前置测试。
- **Allure 测试报告**：为接口请求和响应记录测试附件，并在测试运行后生成 Allure 报告。
- **可选的 AI 辅助分析**：包含失败报告分析、接口响应语义检查，以及面向测试影响分析的工具。相关能力使用规则和开关配置，可选接入外部模型服务。

## 技术栈

Python、pytest、requests、Selenium、gRPC、Allure。依赖版本见 [`requirements.txt`](requirements.txt)。

## 目录结构

| 目录或文件 | 说明 |
| --- | --- |
| `api/` | 业务 HTTP API 封装 |
| `testcase/` | pytest 业务测试用例 |
| `testdata/` | 测试数据及场景定义；部分运行所需数据不在公开仓库中 |
| `common/` | 请求、断言、日志、产品信息和任务依赖等公共能力 |
| `bash/` | Bash 机台通信、gRPC 客户端和推图逻辑 |
| `client/` | 桌面测试客户端源码及打包脚本 |
| `config/` | 配置模板、任务依赖、语义检查规则和 AI 配置 |
| `AI/` | 测试报告分析和接口语义检查 |
| `AI_testing_framework/` | 影响面分析、AI 测试流水线及映射配置 |
| `examples/` | 本地客户端配置示例 |
| `run.py` | 顺序或并行测试调度入口 |
| `pytest.ini` | pytest 标记及测试相关配置 |

## 环境准备

- Python 3.10 或更新版本；建议使用独立虚拟环境。
- 能够访问目标一休云环境的网络及有效测试账号、数据和业务标识。
- 根据测试范围准备 Bash/gRPC 服务、TLS 证书和外部 gRPC 测试客户端，或可用的 Web 环境、浏览器及驱动。
- 若要生成 HTML 测试报告，需额外安装 Allure Commandline。
- 若要使用可选的 AI 分析能力，需按所选模型提供对应 API 凭证。

## 安装与配置

在仓库根目录执行：

```bash
python -m venv .venv
```

激活虚拟环境后安装依赖：

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

python -m pip install -r requirements.txt
```

准备本地配置文件，并根据目标环境填写 URL、账号、密码、Space/设备标识、任务 ID 及数据库信息：

```text
config/env_config.example.ini  ->  config/env_config.ini
bash/json/config.example.json  ->  bash/json/config.json
bash/json/params_data.example.json  ->  bash/json/params_data.json
```

同时根据实际测试范围准备以下本地资源：

- Bash/gRPC 场景所需的授权设备 Token、gRPC 地址，以及 `bash/crt/` 中的 CA 和客户端证书（`ca.crt`、`client.crt`、`client.key`）。
- 测试用文件、外部 gRPC 客户端和测试数据目录。这些资源可能因环境和具体用例而异，未包含在公开仓库中。
- 可选的 `config/secret.env`。根据 [`config/ai_config.ini`](config/ai_config.ini) 中启用的提供方，设置相应的模型 API 凭证。登录 URL、账号等也支持通过 `YIXIU_FAT_...` 和 `YIXIU_PROD_...` 环境变量提供。

本地配置和敏感资源已列入 `.gitignore`。请使用自己的测试环境凭证，不要将账号、Token、私钥或业务数据提交到仓库。

## 运行测试

从仓库根目录执行 pytest。推荐首次先列出用例，确认目标测试依赖的环境已配置：

```bash
python -m pytest --collect-only -q
```

运行全部可发现用例：

```bash
python -m pytest
```

运行单个测试模块，例如：

```bash
python -m pytest testcase/test_product_information.py -v
```

运行单个用例，可按 pytest 的标准选择器进一步限定：

```bash
python -m pytest testcase/test_product_information.py::TestProductInformation -v
```

仓库用例带有业务标记，可用 `pytest --markers` 查看完整列表，再按标记筛选，例如 `python -m pytest -m smoke`。实际运行范围以当前用例所声明的标记为准。

`run.py` 提供项目自定义的顺序和并行调度流程，并负责组织 Allure 结果和后续分析。并行任务通过 `config/task_dependencies.json` 配置；当前运行模块也可能在 `run.py` 中指定，运行前请检查该文件。脚本和测试用例会调用真实业务接口或外部程序，因此请先阅读对应模块并配置测试环境。除语法、收集或适合本地运行的用例外，请勿对未授权的生产环境发起测试。

报告结果默认写入 `report/`，该目录不提交到 Git。安装 Allure Commandline 后，也可直接执行 `allure serve report/allure-results` 查看结果数据。

## AI 测试工具

仓库包含两类不同用途的辅助功能。`AI/` 负责测试报告分析和 HTTP 响应语义检查，规则、基线及运行选项见 `config/semantic_assertion.ini`、`config/semantic_baseline.json`、`config/semantic_suppress_rules.json` 和 `config/ai_config.ini`。`AI_testing_framework/` 则提供代码变更影响分析、算法服务映射以及 AI 测试流水线的相关组件；其使用说明见 [`AI_testing_framework/README_AI.md`](AI_testing_framework/README_AI.md)。这些组件是辅助能力，具体运行仍取决于本地依赖、配置和可访问的模型服务。

## 公开仓库说明

此 GitHub 仓库是经筛选和脱敏后独立维护的公开代码导出。真实环境配置、凭证、证书、业务数据和部分外部测试资源不包含在仓库中。示例账号或标识若出现在代码中，也需按本地环境替换。仓库当前采用 `GH_exclusive` 作为 GitHub 默认分支；私有主线及回归分支保留在 GitLab。跨仓库更新前，应审查待发布代码并移除敏感数据及私有历史。

如需报告问题，提交 Issue 时请提供复现步骤、预期行为和脱敏后的错误信息。请勿公开粘贴访问令牌、账号密码、证书或内部业务数据。
