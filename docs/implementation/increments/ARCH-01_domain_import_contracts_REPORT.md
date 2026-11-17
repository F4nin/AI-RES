# ARCH-01 — Контракты доменных импортов: Increment Report

**Дата:** 2026-11-17 · **Промпт:** [ARCH-01](prompts/ARCH-01_domain_import_contracts.md) · **Статус:** TESTED локально; Linux CI и доставка ожидаются.

## 1. Что реализовано

Два dev-time контракта import-linter закрепляют текущий ациклический граф: три слоя (14 модулей, состав 9/3/2) и независимость девяти доменных peers. Прямые и непрямые обратные зависимости запрещены, верх→низ разрешены; общие слои не объявлены независимыми внутри себя. `exhaustive=true` блокирует новый незаявленный модуль, тест сверяет покрытие верхнего слоя independence. Все 12 прежних контрактов сохранены, новых исключений нет.

10 новых architecture tests проверяют разрешённый граф, обратные слои, peers в обоих направлениях, непрямой обход через внешний для `modules` промежуточный модуль, незаявленный модуль и полноту peer-покрытия. Синтетические пакеты используют точные production-опции, а не дубликат правил.

## 2. Нормативная база и Registry

AGENTS.md с диска целиком (включая §10), CONTEXT_RETENTION, CLAUDE.md, Registry v4.1, Spec v1.22, управление реализацией и применимые rules/ADR. Применимые canonical границы: Spec §3/§8/addenda v1.22–1.22.1; Architecture Concept v4.6 (модульный Backend); Domain Model v1.9 §3 и application service interfaces/domain events. Исторические ссылки разрешаются через Registry. Детерминированная проверка §2: **74 записи, 74 уникальных ID/пути, missing 0**. Полный продуктовый canonical-набор не пересматривался: изменения ограничены конфигурацией dev-time gate и его тестами, требования runtime не меняются.

CI-01 VERIFIED/DONE, что удовлетворяет ADR-114. Начальное дерево чистое; `main`/HEAD `4bdd9043680bdd1622bed65c7506a1726172df23` совпал с read-only `git ls-remote origin refs/heads/main`. Ветка этапа `feat/arch-01-domain-import-contracts`; до первого commit все локальные результаты относятся к этой базе + описанному diff, не к неизменённой базе.

## 3. Созданные и изменённые файлы

| Файл | Изменение |
|---|---|
| `backend/pyproject.toml` | Два новых import-linter контракта |
| `backend/tests/architecture/test_domain_import_rules.py` | 10 behavioral tests с production-опциями |
| `increments/prompts/ARCH-01_domain_import_contracts.md`, `prompts/README.md` | Scope, план, проверки, DoD, индекс мини-этапа |
| `ARCHITECTURE_DECISION_LOG.md` | ADR-120: фактический состав и exhaustive |
| `IMPLEMENTATION_ROADMAP.md` | Ссылка на исполнение уже принятого ADR-114, без перестановки S-этапов |
| `IMPLEMENTATION_STATUS.md`, `CONTEXT_HANDOFF.md` | Текущее состояние и доставка |
| `REQUIREMENTS_TRACEABILITY.md`, `ECC_USAGE.md` | Связь архитектурного требования с gate/tests и фактическое применение ECC |
| `reviews/ARCH-01_REVIEWS.md`, этот отчёт | Исследование, независимые review и evidence |

## 4. API / контракты / события

Публичная поверхность, OpenAPI/AsyncAPI/JSON Schema, зеркало/baseline contracts не изменены. Новые контракты относятся только к Python-импортам при разработке.

## 5. Миграции и совместимость

Ревизии, schema snapshot, роли/RLS и данные не менялись реализацией ARCH-01. Product code и lock/manifests зависимостей сохранены (кроме import-linter секции pyproject). Проверки PostgreSQL/Temporal/Compose выполняются штатным полным pre-pr. Он использует временные Testcontainers и локальный dev-стек; существующие volumes не удаляются. Runtime suite может создавать синтетические данные; неизменность всего содержимого dev-БД не заявляется.

## 6. Самостоятельные решения

ADR-120 ACCEPTED в пределах разрешённого уточнения ADR-114: текущие 14 модулей вместо предварительных 15, три группы 9/3/2, `:` внутри групп, отдельный independence, exhaustive без ignores. Установленные import-linter **2.16**, grimp **3.19**, существующий lock; новые библиотеки не нужны.

## 7. Несогласованности / NCP

Уточнение количества модулей — техническое, не конфликт BASELINED. NCP и новые owner decisions не требуются. Отложенные backup/два инфраструктурных сценария и ограничения S16/SLICE-01 сохраняются. KNOWN_GAPS и DECISIONS_PENDING не менялись: новых нерешённых вопросов в scope нет.

## 8. ECC

`architect`: отдельное read-only исследование до реализации. `code-reviewer` + `pr-test-analyzer`: два отдельных blind-first read-only review, 0 findings; профильный reviewer обнаружил 3/3 мутации. `verification-loop`: явно прочитанный checklist основного исполнителя, использованы соответствующие репозиторию Make/CI команды. Прочие агенты/slash commands не запускались; security/DB review неприменимы к неизменённым runtime механизмам. Evidence — [review](../reviews/ARCH-01_REVIEWS.md), ECC_USAGE. Пробелов обязательного набора нет.

## 9. Проверки

Среда: Darwin arm64, Python 3.13.5, uv 0.11.31; Node 22.23.5/npm 10.9.9, OpenSSL 3.6.3 выбраны только в PATH процесса. Системные Node 26/LibreSSL не использованы для полного прогона, глобальные настройки не менялись. Docker dev project `ai-res`, временные integration-контейнеры; target production не затрагивался.

| Gate / команда | Результат |
|---|---|
| Registry presence/unique check (точная программа ниже) | exit 0; 74/74/74, missing 0 |
| Из `backend`: `.venv/bin/python -B -m pytest -q tests/architecture/test_domain_import_rules.py` | exit 0, **10 passed**, 0 failed/errors/skipped, 1.26 s |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` | exit 0; ruff PASS, mypy 148 source files без ошибок, **14 kept / 0 broken**, **465 passed**, 4 warnings, 0 failed/errors/skipped, pytest 8.80 s |
| Первый `make -j1 pre-pr` с прежним temp Node | exit 2: contracts-check обнаружил неполную временную установку npm (`Cannot find module '../lib/cli.js'`); это не PASS |
| Повторный полный `make -j1 pre-pr` с восстановленным тем же Node | **exit 0**: contracts **22 passed** (7.81 s); backend **1301 passed**, 540 warnings (305.83 s); infra **307 passed** (155.42 s); отдельный runtime **148 passed** (141.38 s); 0 failed/errors/skipped, secret scan 0 findings; ruff/mypy PASS, 14 kept/0 broken. Runtime 148 уже входят в infra 307 и затем исполняются повторно; суммы не являются числом уникальных тестов. |
| `git diff --check` | exit 0 на реализации; финальный повтор перед commit |

Восстановлен только временный инструмент из сохранённого `node-v22.23.5-darwin-arm64.tar.gz`: SHA-256 `e7131995759b61a0170b646010d2ad35a5d37b4cb0d471f3e8317eac6f742f3d` совпал с сохранённым SHASUMS256; npm 10.9.9 проверен. Загрузка/изменение зависимостей проекта не потребовались. Raw local logs в системном temp не являются единственным evidence; постоянная сводка здесь, опубликованные CI URL будут ниже.

Точная повторная команда полного прогона (из корня репозитория):

```sh
PATH="/private/tmp/arch-01-tools/node-v22.23.5-darwin-arm64/bin:/opt/homebrew/opt/openssl@3/bin:$PATH" UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-pr > /private/tmp/arch-01-pre-pr-restored.log 2>&1
```

Registry проверен `infra/.venv/bin/python -B -c` со следующей программой (только чтение):

```python
import re
from pathlib import Path
s = Path("docs/architecture/AI_RES_Document_Registry_v4.1.md").read_text().split("## 2.")[1].split("## 3.")[0]
rows = re.findall(r"^\| (DOC-\d+) \|.*?`([^`]+)`", s, re.M)
missing = [p for _, p in rows if not Path("docs/architecture", p).is_file()]
print({"records": len(rows), "unique_ids": len({i for i, _ in rows}), "unique_paths": len({p for _, p in rows}), "missing": missing})
```

Дополнительные документальные проверки: `infra/.venv/bin/python -B docs/implementation/tools/check_prompts.py` — exit 0, 40 S-промптов/0 issues (ARCH-01 не входит в glob этой утилиты и проверен review вручную); `infra/.venv/bin/python -B infra/scripts/scan_secrets.py` — exit 0, 0 findings. Скан исключает `.claude/` и review-документы по существующей политике; новые review/прочий diff просмотрены вручную, это не скан всей истории Git.

G1/G2/G5/G7/G8/G9 применимы. Новые G3/G4/G6 сценарии не требуются: runtime/API/persistence не меняются; полный регрессионный pre-pr/CI сохраняется. Audit/digests/hadolint/actionlint/SBOM/vulnerability scan проверяются в Linux CI отдельно от pre-pr.

## 10. Security / authorization cases

Новые негативные случаи относятся к статическим import boundaries: обратные слои, peer-импорты в обоих направлениях, непрямой обход и незаявленный модуль. Результат — ожидаемый exit 1 с именем BROKEN-контракта, разрешённый граф — exit 0. Существующие runtime security/authorization cases не изменялись; их регрессия — в полном наборе. Secret scan обязателен до commit, содержимое секретов в отчёте/терминале не выводится.

## 11. Независимое review

Два независимых blind-first reviewer: **CRITICAL/HIGH/MEDIUM/LOW = 0**; исправлений не потребовалось. Test reviewer независимо проверил обнаружение трёх мутаций. Полный [протокол](../reviews/ARCH-01_REVIEWS.md). Security-owner approval продукта этим не заменяется.

## 12. Ограничения

Dev-time gate контролирует статические импорты; не доказывает SQL/table isolation, event semantics, динамические импорты или runtime permissions. При добавлении нового модуля нужна явная классификация. Непрочитанный полный продуктовый стартовый набор не объявляется прочитанным; применимые модульные требования проверены. Production readiness не заявляется.

## 13. Документы и статусы

Обновлены промпт/индекс, ROADMAP-ссылка на уже принятое решение, ADR-120, STATUS/HANDOFF, REQUIREMENTS_TRACEABILITY, ECC_USAGE и review/report. CONTRACT_TRACEABILITY_MAP не менялся: публичные/runtime контракты и persistence mapping прежние. Canonical, Registry, baseline manifest, KNOWN_GAPS и DECISIONS_PENDING сохранены.

## 14. DoD и доставка

Реализация, целевые тесты, быстрый слой, полный локальный pre-pr и два review выполнены. Linux CI по точному опубликованному SHA и Git-доставка ещё не завершены; VERIFIED/DONE пока не присвоены. Существующие Spectral warnings/baseline сохранены; нулевое число warnings не заявляется. Dev-стек поднят штатно, existing secrets сохранены (21 файл, 0 written), volumes не удалялись.

## 15. Следующий безопасный шаг

Завершить gates и доставку ARCH-01, затем остановиться. S17 всё ещё ждёт очередь S16/SLICE-01; прочие блокеры не сняты. Следующий инкремент выбирается по ROADMAP/ADR и новой команде владельца; при отсутствии приоритета между DEP-01, PROF-01 и прочими READY-кандидатами требуется выбор владельца.
