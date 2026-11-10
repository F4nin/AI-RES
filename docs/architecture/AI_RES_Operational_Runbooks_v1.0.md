# AI RES — Эксплуатационные процедуры и Runbooks наблюдаемости

**Версия:** 1.0 | **Статус:** WORKING | **Дата:** 2026-11-10

> Это проектные процедуры. Наличие документа не означает, что команды, dashboards или recovery actions уже реализованы и протестированы.

## 1. Общие правила
1. Зафиксировать incident ID, время, сигнал, affected scope.
2. Определить пользовательское влияние и класс: availability, latency, workflow, quality, integrity, security, telemetry.
3. Сохранить sanitized trace/log refs и версии release/model/prompt/WorkerDefinition/tool.
4. Не копировать secrets или raw payloads в тикеты.
5. Выполнять только разрешённые и обратимые recovery actions.
6. При риске integrity/security остановить опасную операцию и эскалировать.
7. После восстановления сверить domain state, Temporal Workflow, Worker Runs, MinIO refs и external side effects.
8. Закрыть incident с root cause (если установлен), contributing factors, corrective actions и regression candidate.

Severity:
- SEV-1 — существенная недоступность, потеря/повреждение данных, security compromise или неконтролируемый side effect.
- SEV-2 — значительная деградация критичного сценария без полноценного обхода.
- SEV-3 — частичная деградация, отдельные ошибки, telemetry gap без подтверждённого ущерба.
- SEV-4 — косметическая/единичная некритичная проблема.
Severity определяется impact, не названием компонента.

## 2. Сервис недоступен
**Сигналы:** health failure, restart loop, connection failures, 5xx.
1. Проверить Platform Overview и scope.
2. Проверить container state, exit/restart codes, resources, disk.
3. Проверить зависимости PostgreSQL, MinIO, Temporal, LLM Gateway.
4. Изучить первый failure trace/log и недавние release/config changes.
5. Не удалять volumes и не выполнять destructive restart.
6. Выполнить bounded restart только при подтверждённой transient причине и по deployment procedure.
7. При признаках DB/storage corruption перейти к recovery procedure; не запускать миграции автоматически.
8. Проверить health, queues, unfinished workflows и пользовательский сценарий.

## 3. Temporal backlog / stuck workflows
**Сигналы:** queue backlog, schedule-to-start growth, Activity retries, workflow без прогресса.
1. Определить Task Queue (`ai-res-manager` / `ai-res-workers`) и Workflow types.
2. Проверить Temporal, Worker pollers, concurrency/budget и dependencies.
3. Отличить очередь от медленных Activities; сгруппировать по error class/version.
4. Проверить bounded retries/timeouts и отсутствие hot loop.
5. Проверить Human Approval/Readiness Gate — ожидание может быть штатным.
6. Восстановить poller/provider только после подтверждения причины.
7. Не удалять Workflow history и не менять доменное состояние вручную.
8. Reconcile Task/WorkerRun ↔ Temporal Workflow и подтвердить прогресс.

## 4. LLM Gateway/provider деградация
**Сигналы:** latency/error/rate-limit/token-cost surge.
1. Определить provider/model, версии и временное окно.
2. Проверить gateway errors, limits, network/egress и credentials без раскрытия секретов.
3. Сравнить затронутые task classes с baseline.
4. Использовать только заранее разрешённый fallback profile.
5. Ограничить дорогие retries, если предусмотрено budget policy.
6. Если fallback меняет качество/приватность/локальность — запросить human decision.
7. После восстановления сравнить latency, errors, tokens/cost и quality outcomes.

## 5. Ошибки инструментов
**Сигналы:** tool error/timeout/permission-denied surge.
1. Сегментировать по tool/version/operation class.
2. Проверить connector health, rate limits, contract/schema changes и внешние response codes.
3. Различить permission denial и technical failure; запрет не обходить.
4. Проверить idempotency/reconciliation для side effects.
5. Retry только retryable errors и в заданных пределах.
6. При schema drift ограничить операцию и создать integration incident.
7. Проверить отсутствие duplicate side effects.

## 6. Деградация качества / QA failures
**Сигналы:** verification/QA failures, rework, disputes, negative feedback trend.
1. Определить task/artifact type, Worker/model/prompt/tool versions и sample size.
2. Проверить rubric/evaluator/source/context versions.
3. Использовать sanitized traces и evidence refs; один случай не доказывает системный дефект.
4. Выполнить независимую проверку по QA policy.
5. Классифицировать defect: source/retrieval, reasoning, planning, tool, schema, orchestration, UX, evaluator.
6. Создать corrective task и regression candidate.
7. Изменение model/prompt/workflow — только через evaluation, review и controlled release.
8. Не переводить disputed/unverified в verified ради улучшения метрики.

## 7. Telemetry pipeline недоступен
**Сигналы:** Collector export failures, dropped spans/logs, backend ingestion failure.
1. Проверить SDK export errors, Collector health/queue saturation, backend health.
2. Убедиться, что bounded buffering не исчерпал лимит и приложение продолжает работу.
3. Проверить endpoints, TLS/auth, storage capacity без раскрытия credentials.
4. Восстановить pipeline; не увеличивать buffers без оценки ресурсов.
5. Проверить export success и зафиксировать telemetry gap.
6. За gap window проверить Domain Audit Events и Temporal state независимо.
7. Не объявлять потерянную telemetry восстановленной, если её нельзя replay/export.

## 8. Диск/хранилище заполнено
**Сигналы:** disk threshold, MinIO capacity, Loki/Tempo/Prometheus storage errors.
1. Определить filesystem/bucket/backend и класс данных.
2. Проверить retention/compaction/rotation, runaway logs и sampling.
3. Не удалять Audit Log, source/artifact objects или PostgreSQL volumes вручную.
4. Очистить только eligible telemetry по утверждённой retention policy.
5. При нехватке capacity согласовать storage expansion и/или sampling.
6. Проверить ingestion, backup и доступность после очистки.

## 9. Утечка чувствительных данных в telemetry
**Сигналы:** credentials, PII, prompt/source content в logs/traces/Langfuse.
1. Рассматривать как security incident; ограничить доступ к backend/search/export.
2. Зафиксировать scope, signal type, time range, project/tenant и identities with access.
3. Остановить exporter/content capture или pipeline route.
4. Не копировать leaked content в incident ticket.
5. Security owner определяет credential rotation/session revocation/privacy response.
6. Выполнить контролируемое удаление из active backend; оценить backups/exports.
7. Проверить audit access logs.
8. Исправить redaction и добавить regression test.
9. Возобновить export после negative test и approval.

## 10. Backup failure / recovery readiness
**Сигналы:** backup job failure, WAL archive gap, MinIO backup failure, Recovery Manifest mismatch.
1. Проверить последнюю успешную PostgreSQL backup/WAL point и MinIO snapshot/version.
2. Определить фактический RPO exposure; target RPO не выдавать за достигнутый.
3. Устранить причину и повторить backup.
4. Проверить Recovery Manifest ↔ Release Manifest/config.
5. Выполнить восстановление в изолированном test environment.
6. Сверить domain DB, object refs, Temporal workflows, unfinished runs, external side effects.
7. Записать фактические RPO/RTO drill results.

## 11. Drift alert
**Сигналы:** KS/KL/PSI/embedding similarity threshold crossed или quality/retry trend shift.
1. Проверить baseline/current windows, sample size и feature extraction.
2. Проверить data quality, pipeline и сезонность/состав трафика.
3. Сегментировать по project/task/source/model/prompt/tool в рамках ACL.
4. Проверить quality outcomes, retrieval и feedback.
5. Сформировать гипотезы и проверить на выборке.
6. Выбрать corrective action через owner review.
7. Провести evaluation/regression до release.
8. Не запускать automatic fine-tuning/retraining из-за одного alert.

## 12. Rollback после релиза
**Сигналы:** error/latency/quality/safety regression после release.
1. Сопоставить деградацию с release/config/model/prompt/tool changes.
2. Проверить rollback safety по Release Manifest и DB schema compatibility.
3. Если безопасно — вернуть предыдущие image digests/config; DB schema автоматически не откатывать.
4. При несовместимой миграции использовать заранее выбранный forward-fix/restore.
5. Проверить health, Temporal queues, unfinished runs, MinIO refs, external side effects, audit.
6. Создать release comparison и regression candidate.
7. Возобновлять rollout после evaluation и approval.

## 13. Пользовательская обратная связь
1. Проверить feedback category, context и trace ref.
2. Не трактовать implicit signal автоматически как negative rating.
3. Сопоставить с task outcome, QA, latency, tools и source context.
4. Sanitise and review candidate trace.
5. Создать improvement task / evaluation candidate.
6. Зафиксировать disposition; не запускать обучение автоматически.

## 14. Пример структуры alert rule
```yaml
alert:
  name: temporal_worker_queue_backlog_high
  severity: warning
  scope: temporal.task_queue
  condition: backlog_above_calibrated_threshold
  for: calibrated_duration
  owner: platform_operations
  runbook: AI_RES_Operational_Runbooks_v1.0.md#temporal-backlog-stuck-workflows
  user_impact: delayed_worker_execution
  auto_action: none
  silence_policy: deduplicate_by_queue_and_incident
```
Threshold/duration заменяются калиброванными настройками до production.

## 15. Checklist эксплуатационной готовности
- [ ] Назначены owners и escalation routes.
- [ ] Критичные alerts ссылаются на runbooks.
- [ ] Проверены dashboard access и project/tenant isolation.
- [ ] Выполнены synthetic redaction tests.
- [ ] Проверен telemetry backend outage/fail-open behavior.
- [ ] Проверены backup failure и recovery drill.
- [ ] Проверены Temporal backlog/stuck workflow scenarios.
- [ ] Проверены LLM provider outage/fallback.
- [ ] Проверен tool permission denial — запрет не обходится.
- [ ] Проверен telemetry data leak/purge workflow.
- [ ] Проверен rollback с учётом DB migration.
- [ ] Фактические RPO/RTO и telemetry gaps задокументированы.

## 16. Связанные документы
`AI_RES_Observability_Architecture_v1.0.md`; `AI_RES_Monitoring_and_Alerting_Requirements_v1.0.md`; `AI_RES_Agent_Observability_and_Evaluation_v1.0.md`; `AI_RES_Infrastructure_Deployment_Operations_v1.4.md`.
