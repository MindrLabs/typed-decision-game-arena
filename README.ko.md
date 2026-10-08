[English](README.md) · [한국어](README.ko.md) · [中文](README.zh-cn.md)

# typed-decision-game-arena

이 저장소는 typed-decision 모델이 Tetris, Snake, Connect Four, Pong, Breakout을 한 번에 결정 하나씩 플레이하게
하고, 하나로 고정한 프로토콜 아래에서 순위를 매깁니다. 공개된 모든 게임은 리플레이로 다시 볼 수 있습니다.

모든 모델은 [model-compose](https://github.com/hanyeol/model-compose)로 서빙하며 바이트 단위로 같은 텍스트를
읽습니다. 점수는 같은 시드에서 무작위 플레이어(0)와 강한 규칙 기반 기준 플레이어(100) 사이로 환산합니다.
그래서 모델이 추가되어도 다른 모델의 점수는 바뀌지 않습니다. 리더보드와 리플레이 뷰어는 정적 사이트이고,
model-compose가 모델과 함께 띄웁니다.

**상태:** suite v0.1은 정의됐지만 아직 동결되지 않았고, 공개된 모델 결과는 아직 없습니다. 지금 사이트에는
개발용 시드에서 돌린 두 앵커 플레이어만 보입니다.

## 목차

- [플레이어](#플레이어)
- [빠른 시작](#빠른-시작)
- [보드와 게임](#보드와-게임)
- [비교를 공정하게 유지하는 방법](#비교를-공정하게-유지하는-방법)
- [점수](#점수)
- [전체 실행](#전체-실행)
- [모델 추가하기](#모델-추가하기)
- [저장소 구성](#저장소-구성)
- [라이선스](#라이선스)

## 플레이어

typed-decision 모델은 텍스트 하나와 허용된 답 목록을 받아 그중 하나를 고르고, 답마다 확률을 돌려줍니다.
자유 텍스트를 쓰지 않으므로 목록 밖의 답을 낼 수 없습니다.

| 플레이어 | 모델 | 크기 | family |
|---|---|---|---|
| `clef` | [`Cloudflare/clef`](https://huggingface.co/Cloudflare/clef), Qwen3.8-27B 위의 라우팅 헤드와 LoRA | 27B | clef |
| `clef-flash` | [`Cloudflare/clef-flash`](https://huggingface.co/Cloudflare/clef-flash), Qwen3.5-9B 기반 | 9B | clef |
| `kev-9b` | [`jaredpalmer/kev-9b`](https://huggingface.co/jaredpalmer/kev-9b), Qwen3.5-9B-Base 위의 LoRA와 포인터 헤드 | 9B | kev |
| `kev-4b` | [`jaredpalmer/kev-4b`](https://huggingface.co/jaredpalmer/kev-4b), Qwen3.5-4B-Base 기반 | 4B | kev |
| `kev-0.8b` | [`jaredpalmer/kev-0.8b`](https://huggingface.co/jaredpalmer/kev-0.8b), Qwen3.5-0.8B-Base 기반 | 0.8B | kev |
| `nimble-v2` | [`bespokelabs/Bespoke-Nimble-9B-v2`](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B-v2), Qwen3.5-9B 위의 LoRA | 9B | nimble |
| `nimble` | [`bespokelabs/Bespoke-Nimble-9B`](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B), 첫 릴리스 | 9B | nimble |
| `laya-english` | [`convaiinnovations/laya`](https://huggingface.co/convaiinnovations/laya), english 체크포인트(ModernBERT-large) | 421M | laya |
| `laya-typed` | 같은 번들의 typed-decisions 체크포인트 | 421M | laya |
| `laya-multilingual` | 같은 번들의 multilingual 체크포인트(mmBERT-base) | 322M | laya |
| `random` | 합법적인 선택지 중 균등 무작위: 모든 척도의 0 | | 앵커 |
| `reference` | 게임마다 게임 상태를 직접 읽는 강한 규칙 기반 플레이어: 모든 척도의 100 | | 앵커 |

체크포인트와 리비전은 플레이어 목록의 유일한 출처인 [`model-compose.yml`](model-compose.yml)에 고정되어 있습니다.

## 빠른 시작

NVIDIA GPU가 있는 Linux, [uv](https://docs.astral.sh/uv/), git이 필요합니다. 저희는 NVIDIA DGX Spark(GB10,
aarch64)에서 돌립니다. model-compose는 `scripts/model-compose.rev`에 고정된 리비전으로 `uvx`가 가져옵니다.

```bash
git clone https://github.com/MindrLabs/typed-decision-game-arena
cd typed-decision-game-arena
uv sync                                    # 러너
uv run python scripts/setup_runtimes.py    # 한 번만: .runtime/ 아래 모델별 런타임 (가중치는 아직 받지 않음)
scripts/serve.sh                           # 모델 http://127.0.0.1:8380/api, 리더보드 :8381
```

두 번째 터미널에서 모델을 점검하고 개발용 시드 하나를 플레이시킵니다.

```bash
uv run arena smoke --player kev-0.8b       # 게임마다 요청 하나
uv run arena run --board macro --game snake --player kev-0.8b --seeds dev
uv run arena score --seed-set dev
uv run arena export --seed-set dev         # 리더보드 데이터 갱신 후 http://127.0.0.1:8381 열기
```

`uv run arena show --board macro --game tetris`는 모델이 받는 질문을 그대로 출력합니다.

| 첫 실행에서 | 일어나는 일 |
| :---: | --- |
| 런타임 | `setup_runtimes.py`가 model-compose 컴포넌트를 하나씩 따로 한 번 띄워 `.runtime/<player>/`에 패키지를 설치합니다(공유 wheel은 uv가 하드링크). 처음부터 전부 동시에 띄우면 실패할 수 있습니다. [운영 문서](docs/operations.md#once-per-machine) 참고 |
| 체크포인트 | 각 모델은 첫 요청 때 내려받습니다: Kev 0.8B 1.8 GB, Kev 4B 9.5 GB, Kev 9B 19.5 GB(베이스 모델 포함), Clef 55 GB, Clef-flash 19.1 GB, Laya 번들 2.3 GB(체크포인트 세 개 전부). Nimble은 어댑터(0.19 GB)와 Qwen3.5-9B(19.3 GB)를 받아 `~/.cache/models/nimble-merged`에 한 번 병합합니다(18.8 GB) |
| 메모리 | 모델은 120초 동안 요청이 없으면 내려갑니다. 그래서 모든 플레이어를 선언해 두어도 메모리에는 지금 돌리는 모델만 올라갑니다 |

요청 예시:

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

응답은 `{"status": "completed", "output": {"decision": {"move": "straight"}, "fields": {"move": {"scores": {...}}}}}`입니다.
Nimble 플레이어는 같은 질문을 `{"type": "enum", "choices": [...], "description": ..., "choice_descriptions": {...}}` 형식으로 받습니다.

## 보드와 게임

| 보드 | 시간 | 결정 하나의 단위 | 게임 |
|---|---|---|---|
| Macro | 턴제 | 의미 있는 선택 하나: 피스가 놓일 자리, 패들이 지킬 구역, 회전 방향, 둘 열 | Tetris, Snake, Connect Four, Pong, Breakout |
| Frame | 턴제 | 게임의 한 스텝: 키 하나, 또는 패들 밀기 | Tetris, Pong, Breakout |
| Real-time | 모델이 생각하는 동안에도 게임이 진행됨 | Frame 보드와 같되, 모델의 측정된 반응 시간이 지난 뒤 적용 | Tetris, Pong, Breakout |

Tetris, Snake, Connect Four는 이 저장소에서 구현했고, Pong과 Breakout은 sticky action을 켠 Arcade Learning
Environment(Machado et al. 2018)에서 돌립니다. 게임별 규칙, 선택지, 상한은
[docs/suite-v0.1.md](docs/suite-v0.1.md)에 있습니다.

## 비교를 공정하게 유지하는 방법

- **같은 텍스트.** 모든 모델이 같은 상태, 지시문, 선택지 문장을 읽습니다. 그 문장을 감싸는 JSON만 family별
  질문 형식을 따릅니다. 모델마다 따로 만든 프롬프트는 없습니다.
- **조언이 아니라 사실.** 텍스트는 현재 국면과, 선택지마다 둔 직후에 성립하는 사실(지워지는 줄, 앞의 벽,
  즉시 완성되는 4목)만 말합니다. 순위를 매기거나, 추천하거나, 예측하지 않습니다.
- **기댈 순서가 없음.** 선택지는 시드로 섞인 순서로 나오고, 8개를 넘으면 조별 선택과 결승으로 나누는
  토너먼트를 거칩니다. 모든 모델이 같은 절차를 거치며, `arena bias`가 모델마다 위치를 얼마나 따르는지 보고합니다.
- **모두에게 같은 시드.** 개발용 dev 시드와, 동결된 suite에서만 돌아가는 test 시드를 나눕니다.
- **동결된 프로토콜.** `arena suite freeze`가 suite와, 질문이나 점수를 만드는 모든 소스 파일의 해시를 기록합니다.
  트리가 다르면 test 실행이 거부됩니다. 모든 결과는 lock, 체크포인트 리비전, 서빙 설정 해시를 함께 남깁니다.
- **검증 가능.** 모든 결정을 로그로 남기고, `arena verify`가 게임마다 다시 돌려 텍스트, 국면, 점수가 모두
  같은지 확인합니다.

전체 프로토콜은 [docs/methodology.md](docs/methodology.md)에 있습니다.

## 점수

게임마다 test 시드 평균으로 `k = clip((model - random) / (reference - random), 0, 1)`을 계산합니다. 보드의
지수는 그 보드 게임들의 `k` 평균에 100을 곱한 값입니다. 신뢰구간은 시드를 짝지어 다시 뽑는 부트스트랩(2000회)으로
구하고, 쌍별 차이에는 Holm 보정 p값을 붙입니다. Real-time 보드는 Frame 보드의 앵커로 환산합니다.

## 전체 실행

suite를 동결하고 앵커를 돌린 다음, 모델을 하나씩 GPU에 혼자 올려 Macro와 Frame 보드, `arena latency`,
Real-time 보드, `arena bias` 순으로 돌립니다. 마지막으로 `arena verify`, `arena env`, `arena score`,
`arena export`를 실행합니다. 명령어와 이 순서의 이유는 [docs/operations.md](docs/operations.md)에 있습니다.

## 모델 추가하기

1. `model-compose.yml`에 컴포넌트와 workflow를 추가합니다. workflow id가 플레이어 이름이 되고, 체크포인트
   리비전을 고정합니다. model-compose가 `typed-decision` 태스크로 서빙하는 family(clef, kev, laya, nimble)는
   그대로 쓸 수 있습니다. 새 family는 model-compose 드라이버가 먼저 필요하고, `arena/families.py`에 두 줄을 추가합니다.
2. `uv run python scripts/setup_runtimes.py <id>`와 `uv run arena smoke --player <id>`를 실행합니다.
3. [전체 실행](#전체-실행)처럼 돌립니다. 다른 모델의 점수는 바뀌지 않습니다.

## 저장소 구성

```
model-compose.yml        플레이어(각각 workflow 하나)와 정적 웹 UI
suites/v0.1.toml         게임, 상한, 시드; 동결 후 suites/v0.1.lock.json
arena/                   러너: games/, 프로토콜, family 어댑터, 에피소드, 점수, 리플레이, CLI
  games/                 tetris.py snake.py connect4.py (자체 구현), pong.py breakout.py (ALE), 각자 기준 플레이어 포함
site/                    리더보드와 리플레이 뷰어(Vite, React); webui/로 빌드
webui/                   빌드된 사이트와 `arena export`가 만드는 webui/data, model-compose가 서빙
results/                 에피소드 기록, 점수, 지연시간, 환경 (results/README.md 참고)
docs/                    방법론, suite, 운영, 설계 노트
tests/                   엔진, 프로토콜, 러너, 점수, golden 질문
scripts/                 serve.sh, setup_runtimes.py, model-compose.rev
```

개발 점검: `uv run ruff check . && uv run mypy && uv run pytest`. 사이트는
`pnpm --dir site install && pnpm --dir site check && pnpm --dir site build`.

## 라이선스

[MIT](LICENSE). 각 모델은 자체 라이선스를 따릅니다(위 플레이어는 모두 Apache-2.0). Atari ROM은 ale-py에 포함되어
배포되며 해당 조건을 따릅니다.
