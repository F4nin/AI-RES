# ADR-142 — ограниченная tooling composition SLICE-01

**Дата:**2026-11-18. **Статус:** ACCEPTED, технический выбор Implementation Lead
в поручении SLICE-01/ADR-115. Владелец разрешил реальные тесты до10USD суммарно,
регионcn и INTERNAL без ПДн/коммерческой тайны. Это не human profile approval.

## Проблема

Готовый governed gateway и PostgreSQL admission требуют APPROVED profile и exact
managed refs. Старый candidate — намеренно profileless, six synthetic-only
templates, frozen отдельный account10USD/8attempts. Он не принимает Requirements
документ и его ledger не реализует product BudgetLedgerPort. Rebinding прежних
provider facts к новому profile/prompt/config был бы ложным evidence. MFA владельца
теперь реально активирована (AUTH_MFA_ENROLLED SUCCEEDED15:19:39.850519Z).

## Решение в scope ADR-115

- Всё новое исполнение — development tool `backend/scripts/slice01`, вне
  установленного ai_res package; tests в backend/tests. Product code, contracts,
  canonical и текущие Compose services не изменять.
- Заморозить template/code/config/source/body hashes до paid I/O. Prompt ref —
  версия неизменяемого bundle из diagnostic и Requirements templates; source и
  rendered body — отдельные per-request inputs. Bootstrap использует diagnostic
  entry, итоговый public source — Requirements entry того же exact bundle/code/config.
  Это две разные заранее зафиксированные строки шаблона, не один rendered prompt.
- Первый CANDIDATE probe — отдельно разрешённая quarantined development попытка
  DOC-076§3.1, без fake APPROVED, публикации WorkerResult или domain writes.
  Доверенная composition устанавливает actual profile/code/config/template refs
  **до** запроса, observation извлекается из фактического ответа Bifrost.
- После native security/runtime evidence предъявить точные observation,
  expectation, Bifrost acceptance artifact и profile snapshot владельцу. Личная
  identity/profile acceptance — существующими audited services/CLI с MFA и Policy;
  автоматического approve нет. Затем итоговый вызов — существующим
  GovernedLLMGateway/LLMGatewayPort и PostgreSQL ModelAdmissionGuard.
- Tool-only BifrostTransport subclass добавляет проверенное native
  thinking:disabled к observed CHAT request после неизменённого approved-route
  guard. Это не ослабляет status/admission и не меняет product adapter. Actual
  Bifrost→relay bytes доказываются unpaid native-image fixture до live.
- Отдельные ephemeral dev containers/networks используют тот же reviewed pinned
  Bifrost image и его exact integrity template. Alias llm-gateway ведёт к
  узкому SLICE relay на отдельной internal network; ни host ports, ни Docker
  socket у containers нет. Только relay имеет fixed-provider egress/key, request
  content и destination не выбираются моделью. Старый candidate/runtime не менять.
- Relay принимает только immutable exact request-body allowlist; nonstream CHAT,
  no tools/fallback/retries, concurrency1, limits/timeout, auth, fixed public
  api.deepseek.com IP+TLS/SNI. Canonical bytes, которые хешировались для claim,
  передаются через content= без последующего JSON re-encoding.
- Новый10USD account — **tooling spending control**, durable0600 append/fsync/
  flock ledger, не доменная БД и не реализация product budget G145. Инициализация
  единожды, immutable manifest/authorization и exact per-request digests.
  Независимая консервативная резервация2M input+2048output по проверенным peak
  ставкам0.30/1.20 =0.6024576USD на попытку; estimate из gateway не считается
  hard bound. Unknown/cancel/outage удерживают полный резерв и останавливают новые
  attempts; account не сбрасывается при restart или новой сессии агента.
- Reserve ещё не разрешает egress: после live authorization/durable admission
  producer записывает bounded-lived ARM, relay атомарно once-claims только fresh
  ARM и exact body. Частичный/неоднозначный журнал, file/authorization/audit failure
  дают отказ. Изолированная модель не имеет writable доступа к ledger/ARM/secret.

## Результат и проверки

### Итерации эксперимента после первого реального отказа

V1 выполнил diagnostic и governedrequest, обаKNOWN; total0.0014235USD. Identity
валидирована, но tool отказал без сохранённого rawoutput/точнойпричины. Не выдавать
этот тест за успешноеизвлечение. Для V2 сохранять ограниченный privateQUARANTINE
normalizedoutput и отдельную безопаснуюдиагностику до validator; S14 не ослаблять
и причину V1 не угадывать. Logging content в Bifrost/telemetry не включать.

Бюджет — один существующийaccount. Новыйimmutableplan в versions/N с новымиrefs
не инициализируетwallet: отдельная appendAUTHORIZE_VERSION(parentmanifest→child,
exactrequests) под тем жеlock/hash/head/fsync, только безpending/blocked/UNKNOWN.
CAP/rates/history/всеKNOWNрасходы сохраняются; oldrefs/digestsretired, oldruntime
objectsrefuseпослеtransition. Доactivation прежнийruntimeостановлен, SQLIN_FLIGHT0.
Новыйmanifest/code/prompt не перепривязывается к прежнемуproviderobservation:
freshquarantinedconfigurationprobe, actualcurrentgeneration+1 и отдельноеhuman
ACCEPT_IDENTITY черезсуществующиесервисы. УжеAPPROVEDprofile не становится фиктивным
CANDIDATE, не клонируется, не получаетвторогоapproval/statuschange. Это технический
механизм итераций в ранее разрешённом тестировании10USD, не расширение бюджета.

WorkerResult остаётся S14 v1.1 WORKING. Минимальный результат — grounded
SOURCE_ASSERTION findings и tooling-only findingTypes sidecar; типы берутся из
существующего registry, неизвестное сохраняет declared text и UNKNOWN. Domain
registration/approval API не вызываются. Проверяются exact source/version/checksum,
quote within declared line range, request IDs, no secret/tool execution/injection.

Нужны behavioral unit/concurrency/restart/negative suites, native Bifrost fixture,
independent general/Python/security review и применимые gates; отсутствие runtime
evidence не маскировать mock PASS. Прежние model/provider/production approvals
сохраняются. Это не новый этап/обход S17/WorkerRun Gate и не deployment продукта.
