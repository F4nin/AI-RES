# Независимые review G02 · рабочий checkpoint

## Совместная проверка S17/S20/S21 · 2026-11-24

`protected_wiring_review` сверил применимые DoD, G-107 и exact runtime
scope. CRITICAL/HIGH в отключённом контуре не выявлены. MEDIUM по
отзыву полномочий во время загрузки Manager и перед записью Proposal/Plan
закрыты блокировками и повторным допуском в той же транзакции. Текущие
Policy и MFA используются в решении. Сохранены точные ACL на replay.
LOW по консервативной preflight границе срока Principal отмечен в отчёте.
Штатные model authority, G-145 и общий G-107 открыты.
[Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## ADR-185 · закрепление и сканирование native сборки · 2026-11-24

`g02_native_security_review` и `g02_native_code_review` сверили обновления
Go, CVE и фактический граф модулей. Первое review потребовало проверку
инвентаря Go в отчёте Trivy и хеш patch в provenance. Повторное review
подтвердило оба исправления и выполнило 8 проверок парсера. Открытых
замечаний этого прохода нет. Проверенные образы и exit code сканера
относятся к runtime evidence в [отчёте S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## ADR-184 · переход Temporal и защищённая сборка Manager · 2026-11-24

- `protected_wiring_review` подтвердил границы обоих Compose-рендеров и
  выделенный временный PostgreSQL. CRITICAL/HIGH 0. MEDIUM по покрытию drain
  и проверки второго Run закрыт наблюдением реальной запущенной Activity,
  её завершением на stock и проверкой единственной visibility строки по
  Workflow ID. Повторное review сверило точный таймаут и факт сохранения
  новой версии исполнения с кодом Temporal 1.29.7. LOW о синхронных
  запросах probe учтён таймаутом SQL на временном PostgreSQL. Проверены три
  фазы. Восстановление после начала новых native Run остаётся вне evidence
  этой репетиции.
- `g02_native_security_review` проверил границы входа, mTLS, подпись ar2 и
  отсутствие прямого provider/DB доступа. MEDIUM по лишним полям v0.5 и
  возможной подмене назначенного сообщения закрыт проверкой exact текста,
  запретом истории и источников и повторным Compose с двумя отказами.
  Backend фиксирует Proposal только после допустимого входа на успешном Run.
  Production policy/G-145 и отдельная приёмка managed scope остаются.
- `g02_native_code_review` подтвердил сохранность tenant/recipient границ,
  четыре ключа сортировки и раздельные seeks в feed. Сверил 43 644
  синтетические комбинации с эталоном. Generic plan на PostgreSQL проверяет
  обе границы индекса. Исторический запрос источника доставки отдельно
  сохраняет MEDIUM по нагрузке.

## ADR-182/183 · персональная лента и защищённый Compose · 2026-11-23

- `protected_wiring_review` отдельно проверил Compose, назначение identities,
  приватные listeners и изоляцию метрик. Для выпуска ключей
  `proactive_delivery` обнаружил несовместимые с Linux runtime режимы,
  возможность повторной активации отозванного leaf и неполную проверку PEM.
  Исправления подтверждены тестами credentials, SOPS/age roundtrip и
  отдельным Compose на Linux arm64.
- Для ADR-182 `protected_wiring_review` выявил HIGH по объёму проверок
  ленты, а также MEDIUM по продолжению сводки, сохранности обязательной
  доставки при сбое сводки и авторизации после потока тела PUT. В повторном
  read-only review 0 открытых CRITICAL/HIGH. Подтверждены лимит 32 элементов,
  64 поэлементных решений Policy, шифрованный курсор, сохранение уведомления
  и аудита после ошибки digest и повтор Policy под блокировкой перед записью.
  MEDIUM остаётся по пропускной способности. Исторический anti-join ограничен
  получателем и дедлайном, при длинной истории возможен таймаут обязательной
  доставки. Глубокая позиция в одной сводке также может увеличивать SQL scan.
- В post-ACK регрессии проверяющий обнаружил возможность ложного успеха при
  втором ACK. Финальный тест утверждает ровно одно срабатывание инъекции для
  ожидаемых assignment и Run. Reconciler отдельно подтверждает терминальный
  Run, доменный переход, аудит и сохранность истории для Temporal replay.

Команды PostgreSQL, Compose и итоговые результаты зафиксированы в
[отчёте S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## ADR-181/182 · standalone Temporal, Platform и границы S20 · 2026-11-23

- `g02_native_security_review` blind-first обнаружил HIGH: leaf мог быть
  отозван во время долгого poll с выдачей защищённого ответа. Поправка
  повторно проверяет leaf после внутреннего handler и подавляет ответ
  при отзыве. Tagged test моделирует отзыв внутри handler. Live smoke
  подтверждает отзыв на существующем соединении. LOW о некорректной
  форме отрицательного fixture-history теста закрыт полным запросом.
  Повторное review закрыло оба finding, новых HIGH нет.
- `g02_native_code_review` независимо обнаружил гонку и пограничные тесты,
  а также унаследованное отсутствие таймаута установления SQL соединения.
  Проверены исправления и явное отключение eager. Повторное review APPROVE,
  замечания этого прохода закрыты.
- Для bind оба проверяющих подтвердили отдельную конфигурацию, привязку
  к ровно одному адресу, обязательный TLS и отсутствие wildcard. Замечание
  о покрытии закрыто фактическим `getsockname()` в сетевом тесте. Побочная
  правка lifecycle telemetry исключена из scope изменения bind.
- Теми же независимыми ролями отдельно проверены существующие источники
  персонального уведомления и ограничения v0.4. Найдены committed события
  завершения `MANAGER_MESSAGE` с автором. Для прошлых ответов отсутствуют
  штатная авторизованная команда и доказанная классификация точных сведений.
  Решение принято в ADR-182. Это review scope решения, а положительный
  сценарий серверной доставки и истории ещё требует реализации и review.

Review выполнялось read-only. Сверялись pinned upstream Temporal, Go
extension, Dockerfile, Compose и Backend call sites. Результаты запуска
оригинальны для исполнителя и перечислены в [отчёте S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## ADR-180 · reconciliation allowlist

Первый review выявил возможный regression в совместном Plan/Manager native
сценарии и недостаточную независимость unit cases. Оба исправлены.
Security review обнаружил неоднозначные повторные JSON keys; loader и
валидный duplicate-key regression добавлены. Финальные blind-first
повторные code и security reviews — APPROVE, findings open 0.
Code reviewer отдельно подтвердил исправления combined native timeout fixture,
ортогональных allowlist tests и валидного duplicate-key negative case.
Security reviewer подтвердил fail-closed обработку повторных ключей.

## ADR-179 · отдельный signing key назначенной доставки

`epic_review` сначала выявил MEDIUM при upgrade partial secret set и LOW
для нормализации whitespace; оба исправлены. Теперь обновление отвергает
registry без seed и несогласованную пару до сохранения, сохраняет rotation
keys и принимает допустимые разделители shared loader. `epic_security`
потребовал запретить любые дополнительные issuers в выделенном registry;
listener теперь fail-closed проверяет точное множество issuer.
Повторные blind-first reviews: `epic_review` APPROVE, `epic_security`
APPROVE. Статическая проверка reviewers не заменяет наши unit и networked
native результаты в S20 report.

## ADR-178 · приватная передача lease

`epic_review` проверил контракты, migration snapshot, повтор после
потери ответа и разделение entrypoint. `epic_security` выявил гонку
снятия lease. SQL теперь блокирует запись, заново проверяет время
и фиксирует nonce, допуск и аудит до завершения транзакции.
Реальный PostgreSQL проверяет конфликт блокировок и отказ до RPC.
Независимые повторные review дали APPROVE после закрытия замечаний.
Статический review ограничен подтверждённым scope NCP-19.

## ADR-177 · Backend-композиция доставки

`epic_review` проверил точный namespace, повтор Start и Cancel.
Тест повторного Cancel теперь запрещает повторный вызов signal.
`epic_security` проверил происхождение Run и mTLS. Дополнительный
API key и Authorization запрещены до сборки клиентов. Оба замечания
LOW закрыты повторным review. Проверено разделение ролей в стенде.
Для штатной композиции нужен доверенный frontend с проверкой SAN
и отдельный допуск передачи lease между процессами.

## ADR-176 · namespace назначенного Outbox

`epic_review` и `epic_security` независимо проверили связку tenant,
Operation, assignment, namespace, claim, истёкший lease и replay.
Замечание MEDIUM о недоставляемых исторических и новых строках закрыто
явным карантином при backfill, CHECK для новых активных строк и
проверкой сохранённого маршрута при replay. Повторное review обоих
агентов дало APPROVE. Статический review не заменяет runtime evidence.

## ADR-175 · private v5 и неизменяемая выдача

Code и security review разобрали границу SECURITY DEFINER, RLS,
транзакционные блокировки, audit, точный хеш, legacy и Temporal.
В первоначальном SQL неотличимы скрытый и отсутствующий снимки.
Булева проверка теперь запирает назначение и Operation, затем
проверяет физическую запись под владельцем. Захват выполняет те же
блокировки и фиксирует аудит до возврата результата. SQL snapshot
обновлён, в тесте отдельно вычислен ожидаемый хеш старого и нового
Proposal. Оба независимых повторных review дали APPROVE.

## ADR-175 · отдельный запрос метаданных

`epic_review` проверил общий SQL-снимок, точный выбор Operation и
регрессию стабильной версии. В ответ на MEDIUM тест теперь переводит одну
из двух Operation в RUNNING и сравнивает обе версии до и после.
`epic_security` дал APPROVE в границах текущей внутренней проекции.
Проверены связи tenant/Epic/Operation, закрытый набор полей и успешное
чтение после отзыва широких прав в одноразовой PostgreSQL. Оба review
выполнены независимо, read-only и до отчёта автора. Private wiring и
авторизация текущего назначения относятся к будущей проверке.

## ADR-174/175 · Start replay и подготовка снимка Epic

`epic_review` проверил exact CAS, порядок блокировок, идемпотентность и
совместимый обычный replay. Добавлены покрытие policy rule, аудит чтения
и Location в контракте. `epic_security` выявил HIGH с устаревшей сессией
и уточнил границу истечения при ожидании Outbox. SQL заново проверяет
полномочия и MFA-сессию под блокировками, затем срок сессии после
блокировки точной строки. Тест отзыва отклонён без успешного audit.
Повторное security review дало APPROVE. Внутренний typed Epic metadata
одобрен в проверенном scope. Оба review выполнены read-only.

## ADR-171–173 · отмена до ACK, сводки, версия Epic

Code и security review дали APPROVE для отмены до ACK. Проверены exact
binding, права, порядок блокировок, версия, активные WorkerRun и общий
транзакционный audit. Тест использует реальный PostgreSQL и двойник observer.

Code review группировки выявил MEDIUM в расчёте интервалов в локальном
времени. Входы нормализованы в UTC, добавлена регрессия DST. Будущие
некритичные записи остаются ожидающими. Повторное review дало APPROVE.
Версия внутренней проекции детерминирована. Review выполнено read-only.

Read-only review CI подтвердил общую конфигурацию Compose, точные
локальные теги, pinned pulls и ограниченный изолированный runtime
после исправления рабочей директории и команд shell. Security review
Ed25519 подтвердил валидацию SPKI и безопасные сообщения об ошибках.

## ADR-170 · ранняя отмена и допуск Start · 2026-11-21

`epic_review`: проверены блокировки и CAS при cancel-wins и
admission-wins, повтор с тем же ключом, миграция и завершение точного
cancel-wins intent без вызова Temporal. Замечание о карантине валидного
отменённого intent исправлено. APPROVE.

`epic_security`: HIGH в первой реализации, где native metadata gate
писал metadata в нарушение ADR-129. Запись перенесена в tenant Backend с
однонаправленным trigger. Native authority остаётся read-only. APPROVE
для упорядочивания отмены. Отсутствие доказанного Run после исчерпания
попыток и совместная активация остаются предметом G-107. Оба review read-only.

Точечный code review сверки до ACK дал APPROVE. Допуск
`CANCEL_REQUESTED` сохранён в рамках exact assignment, run, версии и
существующей карты terminal failure. PostgreSQL fixture покрывает
коррекцию и повтор чтения страницы. Отдельного PostgreSQL fixture для
неоднозначного `ABSENT` из `CANCEL_REQUESTED` на этом срезе нет.

## ADR-169 · native подтверждение первого Run · 2026-11-21

Code и security review проверили точный ALREADY_EXISTS, первую запись
Temporal, изоляцию History и сохранение статуса для повторов. Оба
выделили HIGH, поскольку outage metadata первоначально выглядел как
окончательный отказ. Исправлено типизированным UNAVAILABLE. Code review
также проверил ограниченный Start reply и многособытийный первый batch.
После исправлений оба дали APPROVE. Дополнительная сверка Workflow ID
и ограничение deadline покрыты Go-тестами и изолированным native fixture.

## ADR-168 · отмена привязанного Run после ACK · 2026-11-21

`epic_review` и `epic_security` независимо проверили native RPC shape и
identity, signed metadata gate, RLS, порядок assignment → Operation, audit
0049, раздельный Outbox и повтор после доменного терминала. Оба дали APPROVE
для отмены привязанного Run. Ревьюеры read-only, Docker не запускали.

В отдельной ветви G-107 выявлен HIGH: после принятого Start до binding
ранний HTTP cancel может перевести ACCEPTED в CANCELLED без доставки
сигнала, а нынешний binder не связывает ранее непривязанный терминал.
Этот сценарий продолжает блокировать включение всей группы. Runtime
evidence для post-ACK не применяется к этой гонке.

## ADR-166/167 · Proposal approval и маршрутизация START · 2026-11-21

- `epic_review`, code/Python. Проверил сохранение неизменяемого хэша у
  существующей PlanVersion, exact lineage, CAS и уникальность решения.
  Уточнено, что ссылка на закрытый Proposal остаётся внутри snapshot и audit.
  Повторный review подтвердил ограниченное чтение тела, скрытие resultRef и
  одинаковый routing filter для claim и quarantine. APPROVE в scope среза.
- `epic_security`, security. HIGH в первичном review: типизированный POST мог
  буферизовать всё тело до проверок. MEDIUM: пользователь с одним
  `operation.read` видел UUID закрытого Proposal. Добавлены bounded stream,
  deadline, повторная session/Policy после чтения и отдельная проверка
  полномочий с привязкой к Operation. Повторный review APPROVE, новых
  CRITICAL/HIGH не заявлено. Claim filter — маршрутизация; обязательные
  mTLS/assignment/Run checks остаются в своём контуре.

Оба review read-only и blind-first. Защищённая отмена и эксплуатационный
namespace штатного защищённого dispatcher сохранены в G-107.

## ADR-165 · проекция Epic и публичный черновик PlanVersion · 2026-11-21

| Review | Первичный результат | Исправление и приёмка |
|---|---|---|
| General/Python/PostgreSQL, `epic_review` | Проекция выполняет один запрос. Нужно отличать исходное взаимодействие Proposal, сам тест должен покрывать другой проект той же организации и отсутствие GUC. Для публичного draft отсутствовали обязательные CAS и Policy matrix row. | Добавлены `interaction_id`, проверки RLS и `asdict`, `expectedVersion`, атомарный `UPDATE` с `412`, отдельная Policy matrix и тест конкуренции/replay. Независимый повторный APPROVE. |
| Security, `epic_security` | Tenant joins и FORCE RLS проекции проверены. HIGH в новом POST: решение доступа могло устареть при чтении медленного потока. Также нужны deadline и аудит разрешающих read-решений. | Ограничены объём/время чтения. Сессия, Project/Epic и право записи проверяются после потока. Чтения аудируются в транзакции. Регрессии проверяют реальный отзыв сессии и членства, deadline, Origin/CSRF и объём. Независимый повторный APPROVE. |

Обе проверки read-only и blind-first. Связь проекции с решениями Manager
и полный runtime G02 остаются за пределами этого APPROVE. Сетевой integration
test использует новый POST для подготовки неизменяемой версии, без изменений
в native authorizer.

## Native Workflow Task History из нескольких страниц

`code-reviewer` и `security-reviewer` независимо проверили выдачу Workflow
Task и продолжение в исходниках закреплённого Temporal. Замечание MEDIUM
закрыто. Test server теперь ограничивает `HistoryMaxPageSize`, используемый
обычными Workflow Tasks. Сценарий требует успешных register/check/context
с одинаковым digest для одной Manager Operation. Дополнительно проверены
границы размера, числа страниц, курсора, точный Run и отсутствие нового
клиентского доступа к History. Оба повторных вердикта **APPROVE**.
[Проверки](../increments/S20_project_epic_intake_manager_REPORT.md).

## Native Manager timeout · 2026-11-20

`go-reviewer` — **APPROVE** для test-only среза. Замечание LOW закрыто
проверкой exact scheduled/started event IDs, auditable outcome и двух
текстовых canary в сохранённой истории. Сверены настоящий таймаут, ACK,
изоляция Compose, граница перед обращением к модели и replay. Review
read-only. [Проверки](../increments/S20_project_epic_intake_manager_REPORT.md).

## Native failure transport · 2026-11-20

- `go-reviewer` — **APPROVE**. Сверены Python/Rust/Go descriptors и `cause=3`,
  scope Workflow Task и HMAC witness, отказ от неизвестного enum, точная
  persisted History и SDK replay. Полная страница остаётся условием proof.
- `security-reviewer` — **APPROVE**. Отрицательные тесты покрыли чужую роль,
  namespace, отозванный receipt и альтернативное поле причины. Сверены
  раздельные digest и текущий check, отсутствие произвольного payload и
  сохранение запрета observer History. Native timeout witness отдельно открыт.

Review read-only. [Проверки](../increments/S20_project_epic_intake_manager_REPORT.md).

## S20/S21 · effect reconciliation после ACK · 2026-11-20

- `security-reviewer` — **APPROVE** после исправления MEDIUM. `started_at`
  сохраняет provenance ACK при requeue, включая проверку в pre-ACK applier.
  Проверены tenant/RLS, exact scope, lock order, audit insert-only и
  однократный RPC за проход.
- `code-reviewer` — **APPROVE**. Сверены реальные lock paths Task и
  Operation, отмена и приоритет ошибки, частичные эффекты, повтор/Outbox
  и rollback. Закрыт LOW по неопределённому ACK у pure helper. Audit key
  привязан к точной версии наблюдения.

Оба review read-only. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## S20/S21 · статус точного активного Run · 2026-11-20

- `security-reviewer` — **APPROVE** после исправлений. MEDIUM по возможному
  обходу фильтра при redirection закрыт общим startup guard локального
  кластера с явным `noop`. LOW по истечению credential закрыт откатом и
  отдельным аудитом `EXPIRED_OR_REPLAY`.
- `code-reviewer` — **APPROVE** после исправлений. Сверены цепочка
  Temporal interceptors, exact assignment и state SQL, отказ History,
  List и Cancel, обе подписи ar2, старый action ADR-151. LOW по гонке срока
  при выдаче task receipt закрыт дополнительной проверкой в транзакции и
  детерминированным PostgreSQL тестом отката выдачи.

Оба review read-only. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## S20/S21 · общий guard утверждения · 2026-11-20

`code-reviewer` и `security-reviewer` — **APPROVE**, новых замечаний нет.
Сверены отказ сервиса и истёкшей сессии, `ALLOW`, constant-time hash,
точная Policy в HTTP Plan, tenant, уникальность решения и существующий SoD
для Proposal. У Proposal проверен репозиторий. Отдельная команда решения
Proposal и продуктовый producer PlanVersion остаются открыты.
[Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md),
[отчёт S21](../increments/S21_plan_task_orchestration_REPORT.md).

## S20 · подписанный Manager input v0.4 · 2026-11-20

- `code-reviewer` — **APPROVE**. LOW по wire cap закрыт поддержкой 12 байт
  на экранированный символ вне BMP. LOW по разбору непустой истории закрыт
  тестом клиента с OPEN и ANSWERED и негативными ответами.
- `security-reviewer` — **APPROVE** для пустой истории. Проверены подпись
  точного пути, отсутствие раскрытия журнала, конечный лимит и `no-store`.
  Для выдачи записей нужны подтверждённые текущие Policy/ACL и классификация.

Оба review read-only. [Отчёт S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## S20/S21 · потеря Start и consumer Plan approval · 2026-11-20

- `code-reviewer` — **APPROVE** после исправлений. MEDIUM по отмене
  всей страницы закрыт транзакцией на один Plan. LOW по метрике закрыт
  инкрементом после каждого commit. Тест отменяет второй item после commit
  первого и проверяет продолжение. Потеря ответа Start инъецирована в fixture,
  повторный Dispatcher и PostgreSQL реальные.
- `security-reviewer` — **APPROVE** после исправлений. Separate Plan
  dispatch opt-in закрывает MEDIUM по общему допуску с Manager. MEDIUM
  по аудиту закрыт атомарным `PLAN_EXECUTION_PREPARED` и rollback-тестом.
  Штатный Plan Describe и dispatch остаются в scope приёмки.

## S20 · сети Compose и повтор Outbox · 2026-11-20

- `go-reviewer` / `code-reviewer` — **APPROVE**. Проверены реальный claim/mark,
  переход attempt 1→2, сохранение привязки Run, отсутствие второго Start,
  статическая конфигурация сети и сохранение ранее поддерживаемых профилей.
- `security-reviewer` — **APPROVE**. Аргумент exact origin используется
  tagged network profile. SQLite/loopback сохраняет ограничения. LOW по
  origin/downgrade покрыт позитивными и отрицательными Go-проверками.
  Повторное review подтвердило строгий отказ TLS без сертификата и
  положительный handshake оператора.

Оба review read-only. [Runtime evidence](../increments/S20_project_epic_intake_manager_REPORT.md).

## S20 · private ar2 и PostgreSQL verify-full · 2026-11-20

- `go-reviewer` / `code-reviewer` — **APPROVE**. LOW по точке запуска
  закрыт документацией module invocation. MEDIUM по bind ownership
  закрыт согласованным UID/GID, отдельными tmpfs и записью пользователя.
  Проверены три in-memory случая isolation preflight и шесть Go negatives
  по конфигурации TLS и роли.
- `security-reviewer` — **APPROVE**. MEDIUM по возможному запуску прочих
  stock-сервисов закрыт standalone Compose и проверкой rendered модели.
  Граница credentials подтверждена отдельным native контейнером.
  LOW закрыт allowlist точных readonly mounts и единственного secret CA.

Ревьюеры работали read-only. Runtime evidence отдельно в [отчёте S20](../increments/S20_project_epic_intake_manager_REPORT.md).

## S20 · восстановление Run в тестовом Compose · 2026-11-20

Два независимых blind-first read-only review проверили дельту на
`7f0c29f9519217dba722ad1f5b6396d8a02216da`.

- `go-reviewer` / `code-reviewer` — **APPROVE**. MEDIUM по правам bind mount
  закрыт согласованием UID/GID на Docker Desktop и обычном локальном Linux.
  MEDIUM по cleanup закрыт обязательным вызовом `down` до итогового PASS.
  Сравнение с исходным хэшем подтверждено в повторном review.
- `security-reviewer` — **APPROVE**. LOW по PostgreSQL session закрыт
  прямым входом как `temporal_probe`. LOW по файлам verifier закрыт
  выделенным manifest портов, отдельным mount и переносом ключа сервера.

Ревьюеры проверили код и конфигурацию. [Runtime evidence](../increments/S20_project_epic_intake_manager_REPORT.md).

## S20 · PostgreSQL и internode mTLS · 2026-11-20

Два независимых blind-first review проверили рабочий diff на HEAD
`7f0c29f9519217dba722ad1f5b6396d8a02216da`.

- `go-reviewer` / `code-reviewer` — **APPROVE**. MEDIUM по повторному
  использованию данных устранён отдельным контейнером на тест и проверкой
  точного Workflow/Run в visibility. LOW по `MembershipPort` закрыт
  проверкой диапазона для обоих портов и тестом на 40000. `gofmt` прошёл.
- `security-reviewer` — **APPROVE**. MEDIUM по подмене host/database через
  атрибуты DSN закрыт проверкой адреса и отказом от connect attributes.
  Финальная проверка подтвердила DNS SAN, trust anchor, назначение
  сертификатов, loopback и отрицательные сценарии internode handshake.

Открытых замечаний в проверенном scope нет.
[Runtime evidence](../increments/S20_project_epic_intake_manager_REPORT.md).

## S20 · Linux-сборка native Temporal PoC · 2026-11-20

Оба независимых blind-first review проверили дельту к
`7f0c29f9519217dba722ad1f5b6396d8a02216da` в пределах изолированного PoC.

- `go-reviewer` / `code-reviewer` — **APPROVE**. Проверены SHA upstream
  архива и locks, pure-Go SQLite, scratch и provenance. Входы Dockerfile и
  `.dockerignore` включены в хэши, целевой временный рабочий каталог задан
  отдельно. AST/gofmt PASS.
- `security-reviewer` — **APPROVE**. MEDIUM по pprof/metrics, неактивному
  TLS и host overrides закрыт startup проверками и отрицательными тестами.
  Последнее review подтвердило отдельный fetch/verify Go, компиляцию без
  сети и непривилегированный UID с `passwd/group`. Открытых CRITICAL,
  HIGH или MEDIUM в проверенном scope нет.

[Runtime evidence и команды](../increments/S20_project_epic_intake_manager_REPORT.md).

## S20 / G-107 · планировщик сверки до ACK · 2026-11-20

Отдельные blind-first reviewers изучили рабочую дельту на HEAD
`7f0c29f9519217dba722ad1f5b6396d8a02216da`.

- `code-reviewer` / `python-reviewer` — итоговый **APPROVE**. MEDIUM о
  возможном повторении одного начала страницы закрыт частичным курсором.
  PostgreSQL-тест подтверждает прогресс после тайм-аута, повтор отложенного Run
  и однократный аудит. В review 18 focused unit tests, Ruff и mypy, exit 0.
- `security-reviewer` — итоговый **APPROVE**. Проверены mTLS, источник project
  scopes, FORCE RLS, bounded telemetry и остановка. MEDIUM о неожиданном SDK
  enum закрыт typed Describe и regression test. LOW по evidence закрыт
  ожиданием завершённого page span с исходом RUNNING и проверкой audit.

[Тесты и команды](../increments/S20_project_epic_intake_manager_REPORT.md).

## S20 / G-107 · native Describe до ACK · 2026-11-20

Два независимых read-only проверяющих изучили рабочую дельту на HEAD
`7f0c29f9519217dba722ad1f5b6396d8a02216da` без отчёта автора.

- `code-reviewer` / `python-reviewer` с Go-проверкой — **APPROVE**. Схема
  AuthControlClaims пропускала `authorize-reconciliation-describe`, MEDIUM
  закрыт enum и parity тестом. Неблокирующий пробел проверки `revoked_at`
  закрыт отдельным точным запросом до и после коммита отзыва. Ruff, mypy и
  migration graph проверены отдельно, exit 0.
- `security-reviewer` — **APPROVE** для PoC. Проверены verified SAN,
  точный Run, подпись, nonce, boolean definer, узкий EXECUTE, минимальный
  audit и фиксированный текст UNAVAILABLE. MEDIUM по enum закрыт. LOW как
  ограничение evidence: гонка отзыва с уже допущенным native read не проверена.
  Финальная корректировка Operation повторно проверяет версию и назначение.

[Тесты и команды](../increments/S20_project_epic_intake_manager_REPORT.md).

## S20 / G-107 · страница сверки до ACK · 2026-11-20

Проверен рабочий diff от `7f0c29f9519217dba722ad1f5b6396d8a02216da`.
Два отдельных read-only проверяющих сформировали выводы без отчёта автора.

- `code-reviewer` / `python-reviewer` — **APPROVE, findings 0**. Уникальная
  связка Operation–assignment и условие `id > after` сохраняют порядок
  страницы после корректировки. Транзакция закрыта перед RPC. Проверки
  назначения, версии и CAS защищают повтор. Точечные Ruff 0.17.4
  и mypy 2.4.1 прошли, exit 0.
- `security-reviewer` — **APPROVE** в проверенной области. CRITICAL/HIGH/MEDIUM
  findings 0. Запрос параметризован, явный tenant scope подкреплён FORCE RLS
  и составным FK. Финальный `FOR SHARE` и CAS защищают запись при изменении
  привязки или версии. LOW для production-подключения: доверенный планировщик
  устанавливает scope, allowlist, курсор и рабочий верхний предел размера
  страницы. Запуск целевого планировщика и производственная authority
  наблюдателя остаются открытыми.
- `pr-test-analyzer` — **APPROVE** после добавления отдельного `QUEUED` и
  соседнего проекта одной организации. Проверены фактическая коррекция
  `TERMINATED` на реальном Temporal и независимые счётчики audit/Outbox.
  До завершения Run проверка подтверждает отбор кандидата и сохранение статуса.

[Тесты и команды](../increments/S20_project_epic_intake_manager_REPORT.md).

**База:** `7f0c29f9519217dba722ad1f5b6396d8a02216da` + diff
ветки `feat/g02-tool-registry-manager` в отдельных read-only заданиях.
Дата 2026-11-18.

## Дополнение от 2026-11-19

Независимое review нативного PoC выявило HIGH по точному scope Activity
и метаданным SDK. Полный digest операции сверяется в Activity command.
Терминальный результат сверяется с PostgreSQL. Повторное review подтвердило
закрытие двух путей передачи метаданных — произвольных Poll полей и вложенных
protobuf duration fields. Go тесты подтвердили отрицательные случаи, нативный
сквозной сценарий прошёл за 6.70 с. Авторизации native failure/cancel,
общему G-107 и допуску оплачиваемого вызова ещё требуется финальная приёмка.

## S17 и проекция вопросов S20

Первый blind-first проход выявил отсутствие транзакционной границы записи,
owner migration policy, свежей revalidation после ожидания lock и общей
audit correlation. Исправления — `SqlToolWriteExecutor` с savepoint и
idempotency store, scoped FORCE RLS + точная owner policy, lock order
Operation → Run → grant, повторная Policy рядом с apply/replay, общий
correlation ID, исключение выключенного MCP из каталога.

Повторное general/Python/database/test review и отдельное security review
дали **APPROVE, 0 открытых CRITICAL/HIGH** для локального S17 и отдельной
проекции вопросов S20. Production Runtime binding и общий diff G02 ещё
требуют review. Проекция ожидает плотную последовательность событий вопросов,
которую будущий mapper получает из канонических interactions/projections.

## ADR-129 / S20

Security reviewer сверил split `raw_path/query_string` и необходимость
durable nonce до защищённого эффекта. Query теперь отдельный обязательный
аргумент. Native PoC получил literal loopback для frontend/Ringpop, ограниченное
окружение subprocess и Docker bind PostgreSQL с inspect-проверкой. Сам
Temporal использует disposable SQLite только для своего синтетического
workflow; receipt store — реальный PostgreSQL 16.15. Стандартный
Testcontainers cleanup sidecar остаётся инфраструктурой тестов.

PoC evidence покрывает verified SAN, mTLS, native ACL очереди, запись digest
до передачи токена и отказ completion при недоступном receipt verifier.
Полного deployed ADR-129 enforcement, Activity lifecycle и S20 runtime
этот результат не подтверждает.

## Platform v0.3 и S21

Независимый code reviewer подтвердил раздельные ETag и внутренний CAS,
event-backed seal, exact input digest и привязку Plan Tasks. Независимый
security reviewer сверил SQL role, ar2, private TLS, историю Temporal
и scope v0.3. Исправлены повторная проверка срока после lock, metadata audit
выдачи сообщения, read-only replay завершённого draft, запрет TLS keylog
из окружения, строгий формат ответа и обязательная связь Platform Task
с утверждённым пунктом плана. Целевые PG и TLS тесты подтверждают
контроль в проверенном локальном срезе. Review полного runtime остаётся.

## Повторный review после исправлений

General/Python/DB reviewer подтвердил разделение подтверждения запуска и
единственной модельной попытки. Security reviewer подтвердил запрет старого
ar1 для назначенной Operation, replay по сохранённому Run, аудит 0044 и
bounded public intake. По этим исправлениям 0 открытых CRITICAL/HIGH.
Целевой прогон 56 passed / 1 предупреждение включает old/new control, миграции
и локальный сквозной тест. Production native Workflow commands, isolation
и reconciler остаются отдельными обязательными проверками.


## Продолжение S20 · 2026-11-19

Отдельный blind-first `g02_local_review` применил ECC code-reviewer и
python-reviewer к G-107 pre-ACK, DTO и тестам. CRITICAL/HIGH 0. MEDIUM по
приёму некорректных типов в DTO исправлен. Повторное read-only review
подтвердило строгие UUID/enum/str/bool, неизменяемую коллекцию, лимит и
уникальность. Проверен тест контрольной строки адаптивного ответа и replay.

Отдельный blind-first `g02_security_review` проверил точное назначение, RLS,
свежесть версии, отзыв, CAS и аудит, DOC-086 и role map. CRITICAL/HIGH 0 в
локальном срезе. Синхронизированы NCP/DECISIONS и уточнён контракт уникальности.
Security delta review подтвердил повторную проверку exact ar2 после чтения.
При уже зафиксированной отмене черновик и обращение в LLM пропускаются.

Для приёмки остаются действующие per-record Policy/ACL/classification,
правила на производный черновик, проверка между последним ACK и реальным
provider send, purpose-bound observer и общий G-107. В JSON Schema
`uniqueItems` сравнивает объекты, поэтому handler обязан обеспечить
уникальность `questionId` до записи ответа в transport. Оба review были
read-only. Тестовые прогоны выполнил основной исполнитель.
