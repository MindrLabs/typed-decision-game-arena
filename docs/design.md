# 설계 기록 (suite v0.1)

이 문서는 결정이 내려진 순서와 이유를 남기는 내부 기록입니다. 공개용 설명은 [methodology.md](methodology.md)와
[suite-v0.1.md](suite-v0.1.md)에 있습니다.

상태: **구현 완료, 동결 전.** 2026-10-08 KST 브레인스토밍으로 방향을 정했고, 같은 날 구현했습니다. 모델 결과는
아직 없습니다. 게임 상한과 선택지 사실 목록은 dev 시드 파일럿을 본 뒤 `arena suite freeze`로 고정합니다.

## 1. 목표

typed-decision 모델(Clef, Kev, Nimble, Laya …)을 Tetris, Breakout, Pong, Snake, Connect Four로 공정하게 비교하고,
버전 고정 리더보드와 결정 단위 리플레이를 공개합니다. 모델 서빙과 웹 UI는 model-compose가 맡습니다.

빈자리: 기존 typed-decision 벤치(Decision Index, JevBench, S1MB)는 분류와 일관성 과제를 봅니다. 게임을 끝까지
플레이시키는 비교는 데모 수준에 머물러 있습니다(휴리스틱이 상위 후보를 골라 주는 Tetris 데모, 로컬 대 클라우드
latency 비교). Kaggle Game Arena는 LLM을 대상으로 all-play-all과 Bradley–Terry를 씁니다.

## 2. 확정된 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 운영 | 버전 고정 상시 리더보드. suite v0.1의 시드·규칙·렌더러 고정, 새 모델은 workflow 하나 추가 | 앵커 점수라서 모델이 늘어도 기존 점수 불변 |
| 시간 | 턴제가 메인, 반응 지연을 반영한 Real-time 보드 추가 | 결정 품질과 속도를 분리. latency는 별도 열 |
| 결정 단위 | Macro와 Frame 두 보드 | 판단(Macro)과 제어(Frame)를 따로 측정 |
| model-compose | 서빙 + 정적 웹 UI. 게임·러너·채점은 Python | 수천 스텝 루프와 재시도·재현성은 Python이 안전 |
| 엔진 | Pong·Breakout은 ALE, Tetris·Snake·Connect Four는 자체 구현 | Atari 표준, NES ROM은 배포 불가 |
| 선택지 정보 | 중립적인 즉시 결과 사실 + 합법 수 전부, 8개 초과 시 토너먼트 | 휴리스틱 순위 없이 바닥 효과 완화 |
| 참가 모델 | model-compose가 서빙하는 typed-decision 체크포인트 전부(Laya 포함). 새 family는 upstream 기여 후 추가 | Jev 제외 |
| 레포 | `MindrLabs/typed-decision-game-arena`, private로 시작 | 공개 시점은 따로 결정 |

## 3. 구현하며 정한 것 (근거 포함)

**Pong·Breakout Macro: 구역 중앙에 고정.** 처음에는 구역 중앙으로 이동하는 단순 제어기를 썼는데, 패들이 한 스텝에
약 22px씩 움직이고 관성이 있어서(측정: v' = 0.55·v + 10·u) 진동했습니다. 기준 봇 점수도 −15~−18점에 그쳤습니다.
네 가지를 바꿨습니다.
- 제어기를 측정한 동역학으로 몇 스텝 앞을 보는 예측 제어로 바꿨습니다.
- 결정 시점은 공의 방향이 바뀐 뒤 세 스텝이 일관될 때로 했습니다. 튕긴 직후의 한 스텝 변위가 속도를 잘못 알려 주기 때문입니다.
- 구역 안에서 공을 따라가게 하는 방식도 시험했지만, 반응이 늦어(평균 −10.1점) 버렸습니다.
- 대신 구역 중앙에 고정했습니다(평균 −5.6점).

구역 폭은 패들과 공을 더한 접촉 폭에 맞췄습니다(Pong 16 + 4 → 20px, Breakout 16 + 2 → 18px).

**sticky action 0.25.** `tests/test_atari.py`로 두 가지를 확인했습니다.
- sticky 0이면 콘솔이 결정적이어서 시드가 달라도 같은 게임이 나옵니다.
- 0.25이면 시드마다 다른 게임이 됩니다.

Machado et al. (2018)의 표준값이기도 합니다.

**Real-time 앵커 = Frame 앵커.** 1스텝 지연을 받은 Tetris 기준 봇은 계획이 어긋나 0점이었습니다. 지연된 기준 봇을
앵커로 쓰면 정규화가 깨집니다. 그래서 Real-time 보드는 "즉시 반응하는 기준 봇과 무작위" 대비로 환산하고, 앵커는
실시간 보드에서 따로 돌리지 않습니다. 모델에게는 상태 끝에 실시간 안내 한 줄을 붙여, 직전 선택이 이번에 반영된다는
사실을 알려 줍니다.

**지연 의미론.** 패들 밀기는 다음 결정이 올 때까지 유지되고, Tetris 키는 한 번 작동한 뒤 대기합니다(`Task.held`).
지연 k = ceil(측정 중앙값 / 66.7 ms), 최소 1입니다.

**Laya 예산 2048/512.** 기본값(512토큰, 옵션 헤드 192)으로는 설명이 붙은 선택지 8개를 담지 못합니다. 헤드가 넘치면
Laya는 자르지 않고 오류를 냅니다. 그래서 제작사 README가 안내하는 범위 안에서 올렸습니다. `arena laya-cuts`로 측정한
결과, 세 체크포인트 모두 잘리는 부분이 없었습니다(헤드 초과 0%, 상태 잘림 0%, 48토큰 넘는 옵션 0%, 가장 긴 상태
304토큰).

**Nimble v2.** model-compose가 고정한 Nimble 로더로 서빙합니다. 모델 카드에 따르면 선택지 26개 이하에서는 릴리스와
같은 원래 프롬프트(A–Z)를 쓰고, v2 로더의 차이는 확률 온도뿐입니다. 온도는 argmax를 바꾸지 않습니다. 따라서 Nimble이
보고하는 확률은 온도를 적용하지 않은 값입니다.

**런타임 준비.** model-compose는 컴포넌트를 동시에 띄웁니다. 첫 기동 때 같은 family가 공유 클론 폴더
(`/tmp/mindor-git-sources`)에서 같은 GitHub 패키지를 동시에 설치하다 실패합니다. 같은 venv 경로를 공유할 때도
충돌합니다. 그래서 다음과 같이 했습니다.
- 컴포넌트마다 venv를 따로 둡니다(uv 하드링크라 디스크 부담은 작습니다).
- `scripts/setup_runtimes.py`가 하나씩 띄워 설치합니다.

이 경쟁 상태는 upstream 버그 후보이고, 이슈 초안은 보내기 전에 확인을 받습니다.

**메모리.** `on_demand.idle_timeout: 120s`로 유휴 모델을 내립니다. 내릴 때 model-compose가 `gc.collect()`와
`torch.cuda.empty_cache()`를 호출하는 것을 코드로 확인했습니다.

**Connect Four 솔버.** 자체 negamax로 구현했습니다(기준 봇은 깊이 7, 사다리 상대는 깊이 4). 널리 쓰이는
PascalPons/connect4는 AGPL-3.0이라 MIT 저장소에 넣지 않습니다. 매 수가 완전한 해인지 보는 진단은 v0.1에서 제외하고,
즉시 승리를 놓친 수와 즉시 패배를 허용한 수만 셉니다.

**재현성 장치.**
- 자체 SplitMix64 난수열을 씁니다(Python/NumPy 버전 무관).
- suite lock은 소스·패키지·Python 버전의 해시입니다.
- 결정 로그를 바이트 단위로 리플레이해 검증합니다.
- golden 질문 파일로 텍스트 변화를 잡습니다.
- 부트스트랩 인덱스도 자체 난수열로 만듭니다.
- `arena env`로 런타임별 패키지 목록을 기록합니다.
- 결과마다 모델 설정 해시를 남깁니다.

## 4. 검증한 것 (2026-10-08)

- **Python:** ruff, mypy strict, pytest 114개 통과. 엔진 불변식, 비트보드와 단순 구현 대조, ALE RAM과 화면 대조, 프로토콜,
  지연 의미론, 러너 재개·실패 기록, 리플레이 변조 감지(최종 상태 포함), lock이 다른 결과 거부, 점수 재현성, 진단 도구,
  golden 질문을 검사합니다.
- **사이트:** typecheck, eslint, vitest 52개 통과. 빌드는 바이트 단위로 결정적입니다. headless Chromium으로 29개 화면(라이트,
  다크, 375px)을 확인했고 콘솔 오류 0.
- **새 체크아웃에서 CI 재현:** Python, compose 검증, 사이트(커밋된 빌드 최신 여부)를 돌려 모두 통과.
- **dev 시드 기준 봇:** 62판 리플레이 검증 불일치 0. 엔진·텍스트를 고친 뒤에는 검증기가 낡은 기록을 정확히 잡았습니다.
- **실제 model-compose 서버 스모크 테스트:** 게임 8종 모두 유효한 선택과 확률이 돌아왔습니다.
  - kev-0.8b(choice 형식): 요청당 60~100 ms
  - laya-english(choice 형식): 약 30 ms
  - nimble(enum 형식): 약 250 ms
- **kev-0.8b 짧은 실제 판:** 리플레이 불일치 0. 이 과정에서 Snake 벽 선택지의 존재하지 않는 좌표 문제를 찾아 고쳤습니다.
- **전체 서버 동시 기동:** workflow 10개, 정적 웹 UI, 데이터 응답 확인.

## 5. 남은 일

1. dev 시드 파일럿(모델 몇 개)으로 비용과 바닥·천장 효과를 확인한 뒤 `arena suite freeze`.
2. test 시드 실행: 앵커, 모델 하나씩, latency, Real-time, bias, verify, env, score, export.
3. 결정 로그 공개 위치(예: HF dataset) 결정.
4. 새 family upstream 기여 후보(PR마다 사전 승인): NeoHorse-Jev-4B, AutoJev-27B, 그 밖의 Decision Index 상위 공개 모델.
5. model-compose 첫 기동 설치 경쟁 이슈 초안.
6. GitHub 저장소 생성, push, 공개 전환: 매번 사전 승인.
