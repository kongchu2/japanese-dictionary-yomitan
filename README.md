# JMdict-ko — Yomitan용 일한사전

[Yomitan](https://github.com/yomidevs/yomitan)에서 쓰는 **일본어→한국어** 사전입니다.
[JMdict](https://www.edrdg.org/jmdict/j_jmdict.html)의 표제어, 읽기, 품사, 뜻 구분을 그대로 쓰고, 각 뜻을 LLM으로 한국어로 번역했습니다.

| 파일 | 내용 |
|---|---|
| `jmdict-ko.zip` | 단어 사전. 한국어 뜻, 품사·용법 태그(한국어), 영어 원문(접힘), 참조 링크 |
| `kanjidic-ko.zip` | 한자 사전. 한국 한자 훈음(배울 학), 한국 한자음, 음독·훈독, 획수·학년 |

## 설치

1. [Releases](../../releases/latest)에서 `jmdict-ko.zip`과 `kanjidic-ko.zip`을 받습니다.
2. Yomitan → 설정 → 사전(Dictionaries) → 가져오기(Import)에서 zip을 불러옵니다.
3. 새 버전은 Yomitan의 사전 업데이트 확인으로 받을 수 있습니다(저장소가 공개된 경우).

활용형도 검색됩니다(`食べた` → 食べる, `勉強した` → 勉強).

## 번역 품질

- 한국어 뜻은 LLM(Claude) 자동 번역이라 오역이 있을 수 있습니다. 항목마다 영어 원문(JMdict)을 접어 두었으니 확인용으로 쓰세요.
- 모델이 확신하지 못한 항목에는 `※ 자동 번역 신뢰도 낮음` 표시가 붙습니다.
- 오역 제보와 수정 PR을 환영합니다. `translations/terms.jsonl`에서 해당 JMdict id 줄의 `s`(뜻별 한국어 목록)를 고치면 됩니다.

## 직접 빌드하기

Python 3.9 이상, 그리고 번역할 때는 [Claude Code](https://claude.com/claude-code) CLI(`claude`)가 필요합니다.

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python -m jako fetch                         # JMdict/KANJIDIC2 + Yomitan 스키마 다운로드
.venv/bin/python -m jako translate tags                # 품사·용법 태그 한국어 라벨
.venv/bin/python -m jako translate terms --limit 1000  # 빈도순으로 미번역 엔트리 번역 (재실행하면 이어서)
.venv/bin/python -m jako translate kanji               # 상용·인명용 한자 훈음
.venv/bin/python -m jako build                         # dist/*.zip
.venv/bin/python -m jako validate                      # Yomitan 스키마 검증 + 활용 규칙 확인
.venv/bin/python -m jako review -n 200                 # review/sample.md 에 검수용 샘플
```

- 번역 결과는 `translations/`에 JMdict id 단위로 쌓입니다. JMdict에서 뜻이 바뀐 엔트리는 다음 `translate` 때 다시 번역되고, 그 전까지 빌드에서 빠집니다.
- `build --include-untranslated`를 붙이면 미번역 엔트리도 영어 뜻으로 포함합니다.
- GitHub Actions(`.github/workflows/release.yml`)가 매일 최신 JMdict로 다시 빌드합니다. 내용이 바뀐 경우에만 릴리스를 만듭니다. 번역은 로컬에서 돌리고 `translations/`를 커밋하세요.

## 라이선스

- 사전 데이터(`translations/`, 빌드된 zip): [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
  JMdict와 KANJIDIC2의 파생물입니다. 원본 © [Electronic Dictionary Research and Development Group](https://www.edrdg.org/edrdg/licence.html).
- 번역 순서를 정할 때 쓰는 빈도 데이터: [wordfreq](https://github.com/rspeer/wordfreq) (CC BY-SA 4.0). 빌드 결과물에는 포함되지 않습니다.
