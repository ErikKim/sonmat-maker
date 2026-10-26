# 멈춘 도구 (2026-10-26 보관)

10-18 에 앱(`sonmat`)과 메이커를 레포로 나눈 뒤로 돌지 않던 도구들. 모두 메이커 폴더 안에 있던 앱 사본
(`hapticsd.py`·`recipe.py`·`tools/soundprep.py`·`dshaptics.py`)을 import 하는데 그 사본이 나눌 때 빠졌다.
10-26 앱 리팩터링(엔진 = `sonmat/tools/engine/`, 소리 준비 = `sonmat/tools/soundprep/`)으로 그 이름들도 바뀌었다.

| 파일 | 하던 일 | 왜 안 도나 |
|---|---|---|
| `tools/sim_daemon.py` | 패드·게임 없이 엔진을 돌려 맥에서 앱 창을 시험 | 메이커 루트의 `hapticsd.py` |
| `tools/replay_mame.py` | MAME 이벤트 기록을 엔진에 넣어 무엇이 울렸을지 보고 | `hapticsd.py`·`recipe.py` 를 복사하려 함 |
| `tools/clip_to_recipe.py` | 진동 클립 → 숫자 레시피(게임 소리 없이 느낌을 배포) | 메이커 루트의 `recipe.py` |
| `tools/fmod_ids.py` | 세키로 FMOD 훅의 소리 번호 → 이름 표(`fmod_ids.json`) | 메이커 `tools/soundprep.py`. 세키로 표는 이미 게임 레포에 있음 |
| `dll/inject_nier.py` | 니어에 훅 DLL 손으로 주입 | `hapticsd.py`. 지금은 설치가 로더(`version.dll`)로 넣음 |
| `dll/inject.py` | 훅 DLL 손으로 주입(초기판) | 더 옛 이름 `dshaptics.py` |

다시 쓰려면: 앱 경로를 `sys.path` 에 넣고(`sonmat/` 와 `sonmat/tools/`) `import hapticsd`(그대로 있음), `from engine.recipe import ...`,
`import soundprep` 로 고치면 된다. 시험용 바꿔 끼우기는 `hapticsd.patch(이름, 값)`(모듈이 나뉘어 `m.x = ...` 로는 안 먹음).
