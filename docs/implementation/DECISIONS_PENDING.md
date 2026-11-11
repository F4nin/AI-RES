# DECISIONS_PENDING — только решения владельца проекта / security owner

Технические решения, принятые Implementation Lead в пределах полномочий, сюда не входят — см. `ARCHITECTURE_DECISION_LOG.md`. Прежние DP-01, DP-02, DP-03, DP-05, DP-10 закрыты как ACCEPTED (ADR-008, ADR-011/012, ADR-016, ADR-014, ADR-015) по делегированию из Master Implementation Initialization.

| ID | Вопрос | Кто решает | Блокирует | Почему не может решить Implementation Lead | Безопасный вариант до решения |
|---|---|---|---|---|---|
| OD-01 | Провайдер/модель LLM первого vertical slice и разрешение на передачу данных проектов внешнему провайдеру (egress); приёмка Bifrost PoC | Владелец + security owner | **S16** (и транзитивно S33, S34, S37, S39) | Внешний egress проектных данных, затраты, договор с провайдером — бизнес/безопасность (DOC-076 §5, §7) | S15 провайдер-нейтральный port + test double только в test-профиле (ADR-022, ADR-031) |
| OD-02 | Числовые параметры: пороги и размеры выборок evaluation, human calibration; SLO/capacity; retention/legal hold; alert routing | Владелец (+ юрист для retention) | **S33**, **S38**; production | Registry: WORKING; Spec Add. v1.20 п.8 запрещает изобретать | Конфигурация без значений; автоматическое удаление выключено (ADR-030) |
| OD-03 | Wire names `ai_res_session` / `X-CSRF-Token`; security review Bifrost; приёмка ECC trust assessment | Security owner | Релизный baseline (не старт этапов) | Spec Add. v1.11 | Имена конфигурируемы; используются предложенные |
| OD-04 | Normative Change Proposals NCP-01…NCP-08 (обновление Spec, DDL, Blueprint, DOC-007 статус, AsyncAPI, OAS, Registry) | Владелец | Синхронизацию baseline (не старт этапов) | Изменение нормативных документов | Реализация следует ACCEPTED ADR; расхождения перечислены в NCP |
| OD-05 | Quantitative risk calibration и organization authority matrix (DOC-051 WORKING) | Владелец | Сокращение ручной эскалации в S24–S26 | Бизнес-полномочия | ADR-029: автономно только детерминированно LOW-risk, остальное — человеку |
| OD-06 | Фиксация в git подготовленных файлов (`.claude/` ECC, `docs/implementation/`, правки CLAUDE.md и правила БД) | Владелец | — | Commit только по явной просьбе | Файлы в рабочем дереве |
| OD-13 | Форма `dataschema` (сейчас WORKING: `urn:aires:schemas:<CloudEvents type>`) и `source` WorkerRun-событий (`urn:aires:worker-runs`); решения по NCP-09…11 (расхождения Event Model / API Contracts / State Machine с AsyncAPI v1.6) | Владелец | Фиксацию форм до S10 (dispatcher/SSE); не блокирует S05 | Нормативные документы значений не задают; выбор — изменение контракта | Значения централизованы в `modules/events/envelope.py`, ADR-054 |
| OD-14 | Словарь и граф статусов ArtifactVersion (расхождение G-71), словарь статусов Change Request и требование «CR одобрен» для baseline, разделение автора и утверждающего правила, нужен ли review перед APPROVED артефакта (G-72) | Владелец | До S26 (артефакты) / S31 (change control) | Нормативные документы значений не задают | Реестр статусов в БД (`artifacts.artifact_version_statuses`), минимальный граф, ADR-060 |

## Закрыто решением владельца 2026-11-11
| ID | Решение |
|---|---|
| OD-07 | Выбор делегирован Implementation Lead → ADR-037: детерминированные проверки + независимые ИИ-ревью + adversarial тесты на каждом P0-этапе; подпись security owner — один раз перед релизным baseline (S37) |
| OD-08 | Выбор делегирован → ADR-036: checkpoint-broker в API, роль `ai_res_checkpointer` только на schema `langgraph`, у Worker нет DB credentials |
| OD-09 | Владелец: проектировать недостающие endpoint по информации проекта → ADR-009 (дополнение) и ADR-038: overlay WORKING в `contracts/*/extensions/` |
| OD-10 | Подтверждено владельцем: FastAPI (ADR-008), правки CLAUDE.md и `.claude/rules/database-and-migrations.md` |
| OD-11 | Закрыто 2026-11-11 по просьбе пользователя: из `.claude/settings.local.json` убраны `Bash(bash *)` и `Bash(brew upgrade *)`; оставлены узкие разрешения (make contracts-*, tools/*.py, git status/diff/log) |
| OD-12 | G-56 (форма CloudEvents-envelope): владелец выбрал вариант A — привести к каноническим сообщениям AsyncAPI v1.6 сейчас (2026-11-11) → ADR-054. Остаточные WORKING-значения см. OD-13 |
