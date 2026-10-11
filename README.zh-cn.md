[English](README.md) · [한국어](README.ko.md) · [中文](README.zh-cn.md)

# typed-decision-game-arena

本仓库让 typed-decision 模型逐个决策地玩 Tetris、Snake、Connect Four、Pong 和 Breakout，在同一套冻结的协议下
排名，并为每一局公开的游戏提供回放。

所有模型都由 [model-compose](https://github.com/hanyeol/model-compose) 提供服务，读到的文本逐字节相同。分数在相同
种子上按随机玩家（0）和强规则参考玩家（100）之间换算，因此新增模型不会改变其他模型的分数。排行榜和回放查看器是
一个静态网站，由 model-compose 与模型一同提供。

**状态：** suite v0.1 已冻结（lock `17f3ed7e0f66…`）。十个模型的 test 结果在 [`results/v0.1`](results/v0.1)
和排行榜上，每一个决策都在 Hugging Face 数据集 `MindrLabs/typed-decision-game-arena` 中。

## 目录

- [玩家](#玩家)
- [快速开始](#快速开始)
- [榜单与游戏](#榜单与游戏)
- [如何保持比较公平](#如何保持比较公平)
- [分数](#分数)
- [Versus](#versus)
- [完整运行](#完整运行)
- [添加模型](#添加模型)
- [仓库结构](#仓库结构)
- [许可证](#许可证)

## 玩家

typed-decision 模型接收一段文本和一个允许答案的列表，从中返回一个答案，并给出每个答案的概率。它从不生成自由文本，
因此不会答出列表之外的内容。

| 玩家 | 模型 | 规模 | family |
|---|---|---|---|
| `clef` | [`Cloudflare/clef`](https://huggingface.co/Cloudflare/clef)，Qwen3.8-27B 上的路由头和 LoRA | 27B | clef |
| `clef-flash` | [`Cloudflare/clef-flash`](https://huggingface.co/Cloudflare/clef-flash)，基于 Qwen3.5-9B | 9B | clef |
| `kev-9b` | [`jaredpalmer/kev-9b`](https://huggingface.co/jaredpalmer/kev-9b)，Qwen3.5-9B-Base 上的 LoRA 和指针头 | 9B | kev |
| `kev-4b` | [`jaredpalmer/kev-4b`](https://huggingface.co/jaredpalmer/kev-4b)，基于 Qwen3.5-4B-Base | 4B | kev |
| `kev-0.8b` | [`jaredpalmer/kev-0.8b`](https://huggingface.co/jaredpalmer/kev-0.8b)，基于 Qwen3.5-0.8B-Base | 0.8B | kev |
| `nimble-v2` | [`bespokelabs/Bespoke-Nimble-9B-v2`](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B-v2)，Qwen3.5-9B 上的 LoRA | 9B | nimble |
| `nimble` | [`bespokelabs/Bespoke-Nimble-9B`](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B)，第一个版本 | 9B | nimble |
| `laya-english` | [`convaiinnovations/laya`](https://huggingface.co/convaiinnovations/laya)，english 检查点（ModernBERT-large） | 421M | laya |
| `laya-typed` | 同一套件中的 typed-decisions 检查点 | 421M | laya |
| `laya-multilingual` | 同一套件中的 multilingual 检查点（mmBERT-base） | 322M | laya |
| `random` | 在合法选项中均匀随机：所有量表的 0 | | 锚点 |
| `reference` | 每个游戏一个直接读取游戏状态的强规则玩家：所有量表的 100 | | 锚点 |

检查点和版本固定在 [`model-compose.yml`](model-compose.yml) 中，它是玩家列表的唯一来源。

## 快速开始

需要带 NVIDIA GPU 的 Linux、[uv](https://docs.astral.sh/uv/) 和 git。我们在 NVIDIA DGX Spark（GB10，aarch64）上运行。
model-compose 由 `uvx` 按 `scripts/model-compose.rev` 中固定的版本获取。

```bash
git clone https://github.com/MindrLabs/typed-decision-game-arena
cd typed-decision-game-arena
uv sync                                    # 运行器
uv run python scripts/setup_runtimes.py    # 只需一次：在 .runtime/ 下为每个模型准备运行环境（尚不下载权重）
scripts/serve.sh                           # 模型在 http://127.0.0.1:8380/api，排行榜在 :8381
```

在第二个终端里检查一个模型，并让它玩一个开发种子：

```bash
uv run arena smoke --player kev-0.8b       # 每个游戏一个请求
uv run arena run --board macro --game snake --player kev-0.8b --seeds dev
uv run arena score --seed-set dev
uv run arena export --seed-set dev         # 刷新排行榜数据，然后打开 http://127.0.0.1:8381
```

`uv run arena show --board macro --game tetris` 会原样打印模型收到的问题。

| 首次运行时 | 会发生什么 |
| :---: | --- |
| 运行环境 | `setup_runtimes.py` 逐个单独启动 model-compose 组件一次，把依赖装进 `.runtime/<player>/`（共享的 wheel 由 uv 硬链接）。首次就同时启动全部组件可能失败，见[运维文档](docs/operations.md#once-per-machine) |
| 检查点 | 每个模型在第一次请求时下载：Kev 0.8B 1.8 GB、Kev 4B 9.5 GB、Kev 9B 19.5 GB（含基座模型）、Clef 55 GB、Clef-flash 19.1 GB、Laya 套件 2.3 GB（三个检查点）。Nimble 下载适配器（0.19 GB）和 Qwen3.5-9B（19.3 GB），并在 `~/.cache/models/nimble-merged` 中合并一次（18.8 GB） |
| 内存 | 模型空闲 120 秒后卸载，因此可以声明所有玩家，而内存中只有正在运行的那一个 |

请求示例：

```bash
curl -s 127.0.0.1:8380/api/workflows/runs -H 'Content-Type: application/json' -d '{
  "workflow_id": "kev-0.8b",
  "input": {
    "text": "Snake on a 10 x 10 grid. Head at row 5, column 5, heading up. Food at row 2, column 5.",
    "schema": {"move": {"type": "choice", "instructions": "Choose the move for this step.",
      "criteria": {"left": "turn left: the cell is empty", "straight": "go straight: the cell is empty",
                   "right": "turn right: the cell is empty"}}}
  }
}'
```

返回 `{"status": "completed", "output": {"decision": {"move": "straight"}, "fields": {"move": {"scores": {...}}}}}`。
Nimble 玩家以 `{"type": "enum", "choices": [...], "description": ..., "choice_descriptions": {...}}` 的形式接收同一个问题。

## 榜单与游戏

| 榜单 | 时间 | 一个决策是 | 游戏 |
|---|---|---|---|
| Macro | 回合制 | 一个有意义的选择：方块落在哪里、球拍守哪个区间、往哪边转、下在哪一列 | Tetris、Snake、Connect Four、Pong、Breakout |
| Frame | 回合制 | 游戏的一步：一个按键或一次推动球拍 | Tetris、Pong、Breakout |
| Real-time | 模型思考时游戏继续进行 | 同 Frame 榜单，但在模型实测的反应时间之后才生效 | Tetris、Pong、Breakout |

Tetris、Snake 和 Connect Four 在本仓库中实现；Pong 和 Breakout 运行在启用 sticky actions 的 Arcade Learning
Environment 上（Machado et al. 2018）。各游戏的规则、选项和上限见 [docs/suite-v0.1.md](docs/suite-v0.1.md)。

## 如何保持比较公平

- **相同的文本。** 每个模型读到相同的状态、指令和选项句子；只有包裹它们的 JSON 遵循各 family 的问题格式。
  没有任何模型拥有专属提示词。
- **陈述事实，不给建议。** 文本只描述局面，以及每个选项刚执行后成立的事实（消除的行数、前方的墙、立即连成四子）。
  不排序、不推荐、不预测。
- **没有可依赖的顺序。** 选项以带种子的随机顺序出现；超过 8 个时分组淘汰后再决赛。所有模型走同一流程，
  `arena bias` 报告每个模型在多大程度上跟随位置。
- **所有人使用相同的种子，** 开发用 dev 种子，test 种子只能在冻结的 suite 上运行。
- **冻结的协议。** `arena suite freeze` 记录 suite 以及所有影响问题或分数的源文件的哈希；工作树不一致时 test 运行会被拒绝。
  每条结果都记录 lock、检查点版本和服务设置的哈希。
- **可验证。** 每个决策都有记录；`arena verify` 重放每一局，要求文本、局面和分数完全一致。

完整协议见 [docs/methodology.md](docs/methodology.md)。

## 分数

每个游戏在 test 种子上计算 `k = clip((model - random) / (reference - random), 0, 1)`。榜单指数是该榜单各游戏 `k`
的平均值乘以 100。置信区间来自按种子配对的 bootstrap（2000 次），两两差异附带 Holm 校正的 p 值。Real-time 榜单
使用 Frame 榜单的锚点换算。

## Versus

网站的 Versus 页面在同一个种子上比较两个模型：两局并排、按同一位置同步回放（回合制榜单按决策，实时榜单按游戏步），显示带符号的
分差、双方的选择概率、中间的对比栏，以及从日志计算出的字幕（首次得分、领先易手、先结束的一局、追分）。帧榜单和实时榜单上的
Tetris 不参与比较：没有模型能消除一行。Connect Four 在 `duel-v0.1` 套件中由模型直接对弈（每个开局走两局并交换先后手，
`arena duel`），评分为 Elo 尺度的 Bradley–Terry。在 test 开局上（1,800 局，2 局和棋）Clef 以 1881（95% 区间
1841–1935）领先，其后是 Clef-flash 1705 和 Kev 9B 1587；全部评分与对阵记录见 `results/duel-v0.1/scores-test.json`。
规则见 [docs/methodology.md](docs/methodology.md#versus)。

## 完整运行

冻结 suite 后，`uv run arena campaign --seed-set test` 按顺序运行全部内容：先运行锚点，再让每个模型独占 GPU 依次
运行 Macro 与 Frame 榜单、`arena latency`、Real-time 榜单和 `arena bias`。已完成的部分会跳过，失败的对局会重跑，
持续失败的模型会被跳过；用 `uv run arena status` 查看剩余部分。最后运行 `arena verify`、`arena env`、
`arena score` 和 `arena export`，并用 `arena dataset` 把决策日志发布为 Hugging Face 数据集。命令及该顺序的原因见
[docs/operations.md](docs/operations.md)。

## 添加模型

1. 在 `model-compose.yml` 中添加一个组件和一个 workflow。workflow id 就是玩家名；固定检查点版本。model-compose
   以 `typed-decision` 任务提供服务的 family（clef、kev、laya、nimble）都可以直接使用；新的 family 需要先有
   model-compose 驱动，并在 `arena/families.py` 中加两行。
2. 运行 `uv run python scripts/setup_runtimes.py <id>` 和 `uv run arena smoke --player <id>`。
3. 运行 `uv run arena campaign --seed-set test --models <id> --no-anchors`。其他模型的分数不会改变。

## 仓库结构

```
model-compose.yml        玩家（各一个 workflow）和静态网页界面
suites/v0.1.toml         游戏、上限和种子；冻结后为 suites/v0.1.lock.json
arena/                   运行器：games/、协议、family 适配器、对局、计分、回放、命令行
  games/                 tetris.py snake.py connect4.py（本仓库实现），pong.py breakout.py（ALE），各含参考玩家
site/                    排行榜和回放查看器（Vite、React）；构建到 webui/
webui/                   构建好的网站和 `arena export` 生成的 webui/data，由 model-compose 提供
results/                 对局记录、分数、延迟、环境（见 results/README.md）
docs/                    方法、suite、运维、设计笔记
tests/                   引擎、协议、运行器、计分、golden 问题
scripts/                 serve.sh、setup_runtimes.py、model-compose.rev
```

开发检查：`uv run ruff check . && uv run mypy && uv run pytest`；网站：
`pnpm --dir site install && pnpm --dir site check && pnpm --dir site build`。

## 许可证

[MIT](LICENSE)。每个模型遵循其自身的许可证（上表中的玩家均为 Apache-2.0）；Atari ROM 随 ale-py 分发并遵循其条款。
