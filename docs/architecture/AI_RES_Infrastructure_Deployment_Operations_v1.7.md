# AI RES — Инфраструктура, развёртывание и эксплуатация

**Версия:** 1.7  
**Статус:** согласованная концепция инфраструктуры MVP; отдельные параметры реализации и численные эксплуатационные нормативы требуют PoC и уточнения.  
**Назначение:** зафиксировать согласованные решения по локальному развёртыванию, runtime, workflow, хранилищам, резервному копированию, безопасности, LLM Gateway, наблюдаемости, управлению конфигурацией, обновлениям и версиям инфраструктуры.

## 1. Статус решений

В документе различаются:
- **Согласовано** — пользователь явно подтвердил решение.
- **Кандидат / условное решение** — выбран основной вариант, но требуется PoC, аудит или проверка совместимости.
- **Открыто** — точная реализация или параметр ещё не утверждены.

## 2. Стратегия развёртывания

### 2.1. Целевая стратегия

- Долгосрочная стратегия продукта — гибридная: SaaS и отдельная корпоративная On-premises поставка.
- Текущий этап реализации и тестирования — только локальный On-premises.
- Основной механизм развёртывания MVP — Docker Compose.
- Архитектура должна допускать последующую миграцию на Kubernetes без изменения бизнес-логики.
- Kubernetes-манифесты и полноценная поддержка всех режимов развёртывания не входят в MVP.
- Docker Compose и Kubernetes рассматриваются как разные способы запуска одной и той же системы, а не как разные реализации продукта.
- Контейнеры должны быть переносимыми; конфигурация задаётся через environment/config; постоянное состояние хранится вне контейнеров; интерфейсы компонентов не должны зависеть от конкретного оркестратора.

## 3. Архитектура приложения и процессы Runtime

- Применяется модульный Backend с отдельно запускаемыми Runtime-процессами.
- Полноценная микросервисная архитектура не является целью MVP.
- Manager Runtime отделён от Worker Runtime.
- Используется общий пул Worker Runtime, а не отдельный контейнер на каждую специализацию Worker.
- Девять специализаций Worker — логические роли/компетенции; экземпляры Worker Runtime получают конфигурацию роли и выполняют назначенные задачи.
- Worker Runtime должен допускать горизонтальное масштабирование в дальнейшем.
- Connector Platform может первоначально быть модулем Worker Runtime. Context Builder, Artifact Registry, Traceability, Policy Engine и Rules Engine не обязаны быть отдельными контейнерами.
- API не должен блокироваться длительными агентными задачами.
- Manager делегирует выполнение через Workflow Engine и не управляет Docker/Kubernetes напрямую.

## 4. Workflow Engine и агентное выполнение

### 4.1. Согласованный стек

- Temporal — основной Workflow Engine.
- LangGraph отвечает за reasoning и внутреннюю графовую логику агента.
- Temporal отвечает за durable orchestration: длительные процессы, ожидание человека, таймеры, retries, cancellation, resume и управление жизненным циклом выполнения.
- Worker Runtime исполняет LangGraph-графы.
- Celery + RabbitMQ не выбраны для MVP.

### 4.2. Границы ответственности

- Код Temporal Workflow должен быть детерминированным.
- Внешние эффекты, вызовы LLM, БД, файлов и HTTP выполняются через Activities.
- Human decisions передаются через Temporal Signals/Updates после backend authorization.
- LangGraph Interrupts применяются для внутренних пауз графа, но не заменяют основной жизненный цикл Epic/Task в Temporal.
- Повторы ограничены и классифицируются по типам ошибок; Activities идемпотентны там, где это возможно.
- Предусматриваются timeout, heartbeat, cancellation, compensation/reconciliation и аудит.
- Внешние API не считаются exactly-once: применяются idempotency keys и reconciliation.
- В Temporal History передаются ссылки/идентификаторы и компактные параметры, а не большие документы и полные контексты.

### 4.3. Очереди и идентификаторы

Начальные Task Queues:
- `ai-res-manager` — задачи Manager.
- `ai-res-workers` — задачи Worker.

Общий пул Worker Runtime опрашивает worker queue; отдельные очереди для девяти ролей не создаются на старте. Разделение очередей по нагрузке возможно позднее на основании измерений.

Для корреляции используются `project_id`, `epic_id`, `plan_version_id`, `task_id`, `worker_run_id`, `context_package_version_id`, `temporal_workflow_id`, `langgraph_thread_id`.

### 4.4. Локальная эксплуатация Temporal

- Temporal CLI dev server допустим для локальной разработки.
- Для интеграционного/рабочего локального развёртывания используется self-hosted Temporal с persistent storage.
- Temporal Web UI доступен только администраторам и не публикуется в интернет.
- Temporal размещается во внутренней сети.
- Redis не является обязательным компонентом Temporal.
- Конкретная топология внутренних процессов Temporal, Web UI, namespace и процедура schema migrations уточняются при сборке Compose.

## 5. Хранение данных

### 5.1. PostgreSQL

Согласовано:
- Один PostgreSQL instance/container в Docker Compose.
- Отдельные базы `ai_res_db` и `temporal_db`.
- Отдельные роли с least-privilege доступом.
- Независимые миграции доменной БД и Temporal persistence.
- Возможность позднее вынести Temporal в отдельный PostgreSQL instance без изменения бизнес-логики.
- LangGraph Checkpointer использует PostgreSQL; его таблицы/schema отделены от доменных таблиц AI RES.

### 5.2. Redis

- Redis необязателен и подключается отдельным Compose profile.
- Базовая работа AI RES не должна зависеть от Redis.
- Допустимые применения: cache, rate limiting, краткоживущие временные данные.
- Redis не является источником истины для доменного состояния или Workflow state.

### 5.3. MinIO / объектное хранилище

- MinIO с S3-compatible API обязателен для MVP.
- PostgreSQL хранит метаданные, версии, связи, владельцев и ACL.
- MinIO хранит содержимое файлов.
- Предлагаемые buckets (названия предварительные): `ai-res-sources`, `ai-res-artifacts`, `ai-res-worker-results`, `ai-res-exports`, `ai-res-temporary`.
- Файловые объекты неизменяемы/версионируются; новая версия Source или Artifact создаёт новый объект, а не молча перезаписывает старый.
- Включение object versioning не заменяет резервное копирование.

## 6. Состав Docker Compose

Планируемые сервисы:
- frontend;
- api;
- manager-runtime;
- worker-runtime;
- temporal;
- postgres;
- minio;
- reverse-proxy;
- Redis — только при включении соответствующего profile.

OpenTelemetry и стек мониторинга описаны в разделе 10. Дополнительные внутренние компоненты Temporal могут потребовать нескольких процессов/контейнеров в зависимости от выбранной версии и конфигурации.

## 7. Резервное копирование и восстановление

### 7.1. Согласованные параметры

- PostgreSQL backup: pgBackRest + WAL Archiving.
- Текущее место хранения backup: локальный диск.
- Целевой RPO: до 1 часа.
- Целевой RTO: до 4 часов.
- Система на текущем этапе тестируется локально.

RPO/RTO являются целевыми показателями, а не гарантией до проведения регулярных recovery drills.

### 7.2. Ограничения и дополнительные требования

- Backup на том же физическом сервере/диске защищает от части логических ошибок, но не от потери самого сервера или диска. Для локального тестирования это принято как временное ограничение.
- Для будущей рабочей On-premises поставки должна поддерживаться независимая внешняя backup storage без изменения бизнес-логики.
- MinIO objects должны резервироваться отдельно от PostgreSQL.
- Отдельно сохраняются конфигурации, версии правил и инфраструктурные manifests.
- Secrets резервируются отдельно и в зашифрованном виде.
- Recovery Manifest должен связывать PostgreSQL backup/PITR point, MinIO snapshot/version, версии конфигурации и незавершённые Temporal Workflows.
- После восстановления проводится Recovery Reconciliation: проверка БД и файлов, сопоставление Temporal Workflows с доменными объектами, проверка незавершённых Worker Runs и внешних side effects, выявление частичных записей. Неоднозначные случаи передаются Manager/человеку; возобновление допускается после проверок.
- Рекомендуемая для будущего production практика 3-2-1 не входит в текущий локальный вариант хранения.

## 8. LLM Gateway

**Решение пользователя от 10.11.2026:** вариант C — единый Gateway поддерживает внешние API и локальные модели. MVP начинает с одного выбранного режима/провайдера; конкретный provider/model остаётся открытым до PoC.

### 8.1. Архитектурное решение

- Собственный LLM Gateway с нуля не разрабатывается.
- Используется готовый популярный продукт с self-hosted возможностью.
- Единый LLM Gateway должен поддерживать внешние API и локальные модели.
- Manager Runtime и Worker Runtime обращаются к Gateway, а не напрямую к провайдерам моделей.
- В архитектуре AI RES предусматривается внутренний LLM Gateway Adapter/contract, чтобы заменить продукт без переработки Manager и Workers.

### 8.2. Выбранный кандидат

**Bifrost (Maxim AI) — основной кандидат для MVP, но не окончательно утверждённая production-зависимость.** Обязательны:
- Proof of Concept в Docker Compose;
- проверка внешней модели и локальной модели (например, Ollama или vLLM);
- проверка совместимости с LangGraph/LangChain и применяемыми API;
- проверка streaming, structured output, tool calling, retries, fallback и обработки ошибок;
- проверка управления ключами, лимитами, расходами и журналированием;
- аудит актуальных security advisories, исправленных версий, конфигурации и поверхности атаки.

До прохождения проверок Bifrost имеет статус кандидата. Версия продукта должна фиксироваться; обновления — проходить контролируемую проверку, а не автоматически подтягиваться как latest.

### 8.3. Ответственность компонентов

- LLM Gateway выполняет техническую маршрутизацию, взаимодействие с провайдерами, fallback, retries, лимиты и учёт использования в пределах своих возможностей.
- Policy & Permission Engine AI RES определяет, кому, для какой задачи и с какими данными разрешён вызов.
- Rules Engine применяет обязательные правила AI RES.
- Manager выбирает модель/профиль только в рамках разрешённой конфигурации.
- Возможность локальной модели не означает автоматическую локализацию данных: правила маршрутизации и передачи данных должны явно определять, какие данные могут покидать инфраструктуру.

## 9. Сетевая архитектура и безопасность

### 9.1. Логические сети

Предлагается разделить сети Docker Compose:
- **Ingress:** Reverse Proxy, Frontend, API.
- **Application:** API, Manager Runtime, Worker Runtime и внутренние прикладные модули.
- **Data:** PostgreSQL, Temporal, MinIO, Redis.
- **Controlled Egress:** LLM Gateway и Connector Platform для разрешённых внешних endpoint.

Это логическое разделение, а не абсолютная граница безопасности. Сетевое членство контейнера не заменяет аутентификацию, авторизацию и контроль каждой операции.

### 9.2. Согласованные принципы безопасности

- PostgreSQL, Temporal, Redis и MinIO не публикуются во внешнюю сеть.
- Reverse Proxy — единственная публичная точка входа пользовательского трафика.
- Temporal Web UI и MinIO Console доступны только администраторам.
- Manager/Workers не получают произвольный доступ в интернет; внешние вызовы проходят через разрешённые Gateway/Connector операции.
- Сервис-сервис взаимодействие требует аутентификации; доверие только на основании Docker network запрещено.
- Authentication, RBAC и Policy & Permission Engine — разные уровни контроля.
- Для API, Manager, Worker и Connector применяются отдельные service identities.
- Права пользователя не наследуются Worker автоматически: Worker получает явно ограниченные полномочия на проект/задачу/Worker Run/операцию.
- Каждая операция повторно проверяется Policy & Permission Engine; при невозможности проверки — fail-closed для критических действий.
- TLS обязателен на пользовательском ingress; шифрование service-to-service определяется threat model и целевым профилем поставки.
- Доступ к MinIO ограничивается ACL и сервисными учетными данными.

### 9.3. Секреты

- Для MVP предполагается Docker Compose secrets и защищённое локальное хранилище исходных секретов.
- Секреты не хранятся в Git и не передаются в контекст LLM.
- Сервис получает только необходимые ему секреты; Worker — только scoped secrets для конкретного Run.
- Секреты не попадают в логи, traces, Temporal History и результаты Worker.
- Предусматриваются ротация и аудит использования.
- Docker Compose secrets не считаются полноценной корпоративной системой управления секретами.
- Архитектура должна допускать будущий Vault/enterprise Secret Manager adapter.

### 9.4. Изоляция выполнения

- Не запускать контейнеры в privileged-режиме.
- Не монтировать Docker Socket в API/Manager/Worker.
- Контейнеры запускаются не от root.
- Устанавливаются CPU/RAM/time limits.
- Для Worker Run используются изолированные временные каталоги.
- Сетевой доступ ограничивается allowlist/egress policy.
- Недоверенный код выполняется только в отдельной изолированной среде; обычный Worker Runtime не является sandbox.
- Источники и внешние данные считаются недоверенными; prompt injection не меняет системные правила и полномочия.

## 10. Логирование, мониторинг, аудит и наблюдаемость

### 10.1. Согласованный стек MVP

- **OpenTelemetry:** стандарт инструментирования traces, metrics и logs; OpenTelemetry Collector — сбор, обогащение, фильтрация и маршрутизация телеметрии.
- **Prometheus:** сбор и хранение метрик.
- **Grafana:** дашборды и визуализация.
- **Grafana Loki:** централизованные логи.
- **Grafana Tempo:** распределённая трассировка.
- **Prometheus Alertmanager:** маршрутизация технических alert-ов.
- **PostgreSQL AI RES:** доменный Audit Log, отдельный от технических логов.
- **Langfuse:** специализированная аналитика LLM и агентных запусков; рекомендуется подключать отдельным Compose profile/опциональным набором сервисов после базовой интеграции, поскольку он увеличивает инфраструктурные требования.

### 10.2. Разделение назначения

1. Логи фиксируют технические события и ошибки.
2. Метрики отражают состояние, производительность, нагрузку и качество.
3. Traces показывают сквозной путь операции между компонентами.
4. Audit Log фиксирует значимые действия субъектов и изменения доменных объектов.
5. Langfuse предоставляет специализированную аналитику LLM-вызовов и качества агентных запусков.

Langfuse не заменяет OpenTelemetry/Grafana stack. Техническая телеметрия не заменяет доменный аудит.

### 10.3. Сквозная корреляция

При наличии соответствующего контекста события должны связываться через `trace_id`, `project_id`, `epic_id`, `task_id`, `plan_version_id`, `worker_run_id`, `temporal_workflow_id`, `context_package_version_id`, `artifact_version_id`. Высококардинальные идентификаторы не следует использовать как Prometheus labels; их место — logs/traces и доменные записи.

### 10.4. Области мониторинга

- Инфраструктура: CPU, RAM, disk, network, container health, PostgreSQL, MinIO.
- Temporal: queue backlog, scheduling/start latency, retries, Activity failures, stuck/uncompleted Workflows.
- Manager/Workers: duration, failures, blockers, retries, QA outcomes.
- LLM: latency, tokens, cost, provider errors, fallback, time-to-first-token — при наличии метрик/интеграции.
- Бизнес-процессы: длительность Epic, доля принятых результатов, возвраты на доработку, полнота traceability, незакрытые блокировки.
- Backup: успешность выполнения, возраст последней успешной копии, проверка восстановления.

Техническая доступность и качество агентного результата измеряются раздельно.

### 10.5. Audit Log

Audit Log хранится в PostgreSQL AI RES как отдельная доменная сущность/набор таблиц. Для события фиксируются как минимум:
- `event_id`, timestamp;
- actor (user/service identity);
- action/event type и результат;
- объект и его идентификатор;
- `project_id`, если применимо;
- correlation/trace ID и связанные Workflow/Worker Run IDs;
- ссылки на версии и основание/причина, если известны;
- policy decision для операций, требующих авторизации.

Регистрируются значимые пользовательские действия, изменения требований/решений/артефактов/Baseline, управление планами и Worker Runs, выдача/отзыв полномочий, изменение правил/конфигурации, интеграционные операции и административные действия.

Требования:
- append-only модель на уровне приложения и ограничений БД;
- обычные пользователи и Worker Runtime не могут изменять/удалять audit records;
- отдельный контроль доступа к просмотру и экспорту;
- аудит административных операций и чтения чувствительных данных;
- экспорт и проверка целостности должны быть предусмотрены архитектурно.

Audit Log не должен копировать секреты, API keys, полные приватные промпты или чувствительные payloads.

### 10.6. Безопасность телеметрии и retention

- Полные prompts, model responses и содержимое документов не записываются в обычные логи по умолчанию.
- Secrets, access tokens, персональные и чувствительные данные редактируются до отправки в observability backend.
- Сохранение содержимого LLM-вызовов в Langfuse — отдельная конфигурация с учётом прав и политик проекта.
- Доступ к Grafana/Loki/Tempo/Langfuse ограничивается административными ролями.
- Сроки хранения метрик, логов, traces, Langfuse данных и Audit Log задаются раздельно; конкретные значения retention открыты.
- Потеря телеметрии не должна останавливать выполнение AI RES. Критические доменные audit events должны сохраняться надёжно.

### 10.7. Alerting

Минимальные сигналы: недоступность PostgreSQL/MinIO/Temporal/Bifrost; остановка обработки Worker queue; рост ошибок/retries; заполнение диска; сбой backup; нарушение проверки целостности; превышение настроенных LLM token/cost limits; застрявшие Workflow. Пользовательский интерфейс получает нормализованные состояния («задача приостановлена», «требуется вмешательство», «провайдер модели недоступен»), а не поток инфраструктурных alert-ов.

## 11. Управление конфигурацией (Configuration as Code)

### 11.1. Принцип

Конфигурация AI RES управляется как версионируемый код в Git. Развёртывание должно быть воспроизводимым: для каждого окружения можно определить точные версии приложения, контейнерных образов, Compose-файлов, конфигурации, правил и схем данных.

Для MVP выбирается **Git + Docker Compose + декларативные конфигурационные файлы**. Ansible, Terraform, Helm и Kubernetes не вводятся в MVP: текущая цель — локальное On-premises развёртывание на одном узле. Ansible может быть рассмотрен позднее для массового управления несколькими On-premises серверами; Terraform — только если появится потребность управлять внешней инфраструктурой.

### 11.2. Структура конфигурации

Рекомендуемая структура репозитория:

```text
infra/
  compose.yaml
  compose.dev.yaml
  compose.test.yaml
  config/
    defaults/
    schemas/
    environments/
      local/
      test/
  secrets/
    encrypted/
  migrations/
  scripts/
  runbooks/
  releases/
```

Это логическая структура; имена и точное расположение файлов могут быть уточнены при создании репозитория. Не следует хранить реальные незашифрованные секреты в Git.

Конфигурация разделяется на категории:
- **Статическая инфраструктурная:** сети, volumes, ports, healthchecks, resource limits, profiles и зависимости Compose.
- **Окружения:** адреса, режимы, уровни логирования, включённые profiles, лимиты и настройки подключения.
- **Прикладная:** настройки AI RES, Manager/Worker, Temporal, LangGraph, LLM Gateway Adapter, Connector Platform и observability.
- **Политики и правила:** versioned Rules Registry и Policy configuration; активные версии должны иметь явные идентификаторы.
- **Секреты:** credentials, API keys, encryption keys и сертификаты; отдельный жизненный цикл и доступ.

### 11.3. Иерархия и правила конфигурации

1. Системные обязательные ограничения безопасности нельзя ослабить конфигурацией окружения или проекта.
2. Конфигурация поставки задаёт безопасные defaults.
3. Environment-specific overrides могут менять только явно разрешённые параметры.
4. Project-level настройки AI RES применяются через доменные Rules/Policy механизмы, а не через произвольные переменные контейнеров.
5. Секреты передаются runtime только через Docker Compose secrets или эквивалентный защищённый механизм; не через Docker image, Git plaintext, CLI arguments или LLM context.
6. Неизвестные ключи, неверные типы, недопустимые значения и несовместимые комбинации должны приводить к ошибке валидации, а не к молчаливому игнорированию.
7. Конфигурация, необходимая для запуска, должна иметь schema и автоматические проверки. Для JSON/YAML использовать JSON Schema либо типизированные модели приложения; для переменных окружения — централизованный каталог имён, типов, defaults, секретности и допустимых значений.
8. Конфигурация должна быть разделена на runtime settings и build-time settings. Секреты и адреса окружения не встраиваются в образы.

### 11.4. Управление секретами в репозитории

Для шифрования секретов, которые необходимо версионировать вместе с deployment configuration, выбирается **SOPS + age** как дополнительный механизм к ранее согласованным Docker Compose secrets.

- В Git допускаются только SOPS-зашифрованные secret-файлы.
- age private key хранится вне репозитория, с ограниченными правами доступа и отдельной резервной копией.
- При развёртывании секреты расшифровываются на хосте в защищённое временное/операционное место и передаются контейнерам через Compose secrets.
- Расшифрованные файлы имеют минимальные права доступа и не включаются в backup/release artifacts в открытом виде.
- Ротация ключей age и самих credentials выполняется как отдельная операция с аудитом.
- SOPS не заменяет runtime secret manager и не решает проблему защиты скомпрометированного deployment host. Для будущей корпоративной поставки сохраняется возможность Vault/Secret Manager.

### 11.5. Валидация и изменение конфигурации

Любое изменение конфигурации проходит:
1. синтаксическую проверку YAML/JSON/ENV;
2. schema/type validation;
3. `docker compose config` и проверку итоговой объединённой Compose-конфигурации;
4. проверки секретов на отсутствие plaintext и утечек;
5. security checks: открытые порты, privileged, Docker Socket, root, volumes, capabilities, egress;
6. интеграционные/смоук-тесты на тестовом окружении;
7. review и фиксацию change record.

Изменения конфигурации, способные затронуть безопасность, доступность, миграции, сеть, secrets, backup или права, требуют отдельного review и не применяются автоматически.

## 12. Версионирование приложения и инфраструктуры

### 12.1. Разделение версий

AI RES использует несколько независимых, но связанных уровней версионирования:

- **AI RES Release:** единая версия поставки продукта по SemVer (`MAJOR.MINOR.PATCH`) после появления совместимого релизного контракта.
- **Component Version:** версия каждого сервиса/зависимости (API, Manager Runtime, Worker Runtime, Temporal, PostgreSQL, MinIO, Bifrost, observability components и др.).
- **Container Image Identity:** читаемый version tag плюс обязательный immutable SHA-256 digest для всех production-like и воспроизводимых развёртываний.
- **Configuration Version:** Git commit SHA и/или release ID, плюс версия схемы конфигурации.
- **Database Schema Version:** отдельная версия миграций доменной БД, LangGraph checkpoint storage и Temporal persistence.
- **Rules/Policy Version:** точные версии активных системных/организационных/проектных правил и политик.
- **Infrastructure Release Manifest:** единый манифест, связывающий все указанные версии.

Нельзя считать номер версии AI RES достаточным описанием состава поставки: один и тот же релизный номер должен быть связан с точными image digests и конфигурацией.

### 12.2. Фиксация образов

- Запрещено использовать `latest` и плавающие major/minor tags в зафиксированных release-конфигурациях.
- Каждый образ фиксируется по version tag и `@sha256:<digest>`.
- Renovate может предлагать новые tags/digests, но не меняет production deployment самостоятельно.
- Собственные образы AI RES собираются из зафиксированных base images и lockfiles; build metadata включает source commit.
- Для каждого релиза сохраняется список всех прямых и транзитивных компонентов настолько, насколько это возможно по используемым build tools.

### 12.3. Release Manifest

Каждая поставка должна иметь машинно-читаемый `release-manifest.yaml` или JSON, содержащий минимум:
- `release_id`, `ai_res_version`, `release_channel`, `created_at`, source commit;
- Compose configuration version/hash;
- service name, image repository, version tag и immutable digest;
- версии Temporal, PostgreSQL, MinIO, Bifrost, observability components и других инфраструктурных сервисов;
- версии config schema, DB migrations и Rules/Policy packages;
- требуемые feature flags/profiles;
- SBOM reference/hash и vulnerability scan summary;
- image signature verification status/identity, если применимо;
- минимально/максимально поддерживаемые версии зависимостей и compatibility notes;
- backup/recovery prerequisites и migration notes.

Release Manifest сохраняется вместе с релизом и включается в Recovery Manifest. Он не содержит секретов.

### 12.4. SemVer и совместимость

- PATCH — исправления без намеренного изменения публичных контрактов и схем, требующих ручной миграции.
- MINOR — обратно совместимые возможности и расширения.
- MAJOR — несовместимые изменения контрактов, конфигурации или миграций.

До фиксации стабильных API и plugin contracts SemVer применяется к поставке AI RES как ориентир, а не как обещание полной совместимости всех внутренних компонентов.

Версии компонентов фиксируются независимо. Для комбинаций LangGraph/LangChain, Temporal SDK/Server, Bifrost/API и observability stack поддерживается проверенная compatibility matrix. Нельзя обновлять один компонент, если он выходит за пределы протестированного диапазона.

## 13. Обновление компонентов и релизный процесс

### 13.1. Инструмент обновлений

Для автоматического обнаружения новых версий и создания pull requests выбирается **Renovate**. Он отслеживает Docker Compose images, Dockerfiles и поддерживаемые package manifests. Renovate только предлагает изменения; решение о включении в релиз остаётся контролируемым.

Политика:
- PATCH/MINOR — группировать совместимые обновления, запускать CI и интеграционные тесты; автоматическое слияние в production запрещено.
- MAJOR — отдельный PR, обязательный анализ breaking changes и ручное решение.
- Security updates — приоритетная внеплановая проверка; срочность определяется severity, экспозицией и наличием mitigations.
- Digest refresh без изменения версии также рассматривается как изменение артефакта и проходит проверки.
- Нельзя использовать автоматическое `docker compose pull && up` без проверки и утверждённого Release Manifest.

### 13.2. Конвейер обновления

1. Renovate открывает PR с предлагаемыми версиями/digests.
2. CI проверяет формат, конфигурацию, lockfiles, vulnerability reports, license metadata и SBOM.
3. Выполняются unit, integration, smoke и compatibility tests.
4. Обновление разворачивается на локальном integration/test профиле Compose.
5. Проверяются healthchecks, Temporal Workflow lifecycle, PostgreSQL connectivity/migrations, MinIO operations, Bifrost PoC regression и observability.
6. Для изменений с высоким риском проводится backup и подтверждение восстановления/rollback plan.
7. После review обновление включается в новый release manifest.
8. Развёртывание выполняется по runbook с post-deploy verification.
9. Фиксируются результат, отклонения, инциденты и возможность отката.

Для одиночного локального узла полноценный canary rollout не предполагается; применяется staged validation и последовательное обновление сервисов с проверкой health. Для будущих multi-node поставок можно добавить canary/blue-green стратегии.

### 13.3. Классы обновлений

- **Безопасное/обычное:** обновление patch/minor без миграций и изменения контрактов; после автоматических тестов требуется контролируемое включение.
- **Совместимое, но чувствительное:** обновление Temporal, PostgreSQL, MinIO, Bifrost, LangGraph/LangChain или компонентов с persistent state; отдельный compatibility review, backup и regression suite.
- **Несовместимое:** major upgrade, изменение протокола, конфигурационной схемы или DB migration; отдельный upgrade plan, тестовый прогон на копии данных, maintenance window при необходимости и ручное утверждение.
- **Экстренное security:** ускоренный процесс с минимально достаточным тестированием и документированным risk acceptance; нельзя отключать проверку подлинности образа и критические security gates.

### 13.4. Порядок обновления и миграции

- Обновления приложения и инфраструктурных сервисов разделяются, если это возможно.
- Temporal Server и его persistence schema обновляются только по официальной процедуре для выбранной версии; миграции Temporal не смешиваются с Alembic миграциями AI RES.
- Доменная PostgreSQL schema мигрируется собственным migration tool (для Python backend — Alembic, если он выбран в реализации); LangGraph checkpoint schema и Temporal schema имеют отдельные владельцев/процедуры.
- Предпочитать backward-compatible **expand → migrate → contract**: сначала добавить совместимые поля/таблицы, затем обновить приложение и перенести данные, после подтверждения удалить устаревшее.
- Деструктивные миграции не совмещать с первым развёртыванием новой версии.
- Перед миграцией обязательны проверенный backup и тест миграции на копии данных для рискованных изменений.

### 13.5. Откат и восстановление

- Откат приложения выполняется возвратом к предыдущим image digests и предыдущему Release Manifest.
- Конфигурация возвращается к соответствующему Git commit/release; secrets восстанавливаются из зашифрованной версии с соответствующим ключом.
- DB migration не считается автоматически обратимой. Для несовместимых изменений заранее задаётся стратегия: backward-compatible rollback, forward-fix или восстановление backup/PITR.
- Откат образа не должен запускаться, если новая схема БД уже несовместима со старым приложением.
- После отката проверяются health, очереди Temporal, незавершённые Worker Runs, MinIO references, external side effects и Audit Log.
- Все операции rollback/recovery журналируются.

## 14. Безопасность цепочки поставки ПО

Для MVP вводится базовый контроль supply chain без построения отдельной платформы:

1. **SBOM:** формировать Software Bill of Materials для собственных релизных образов и сохранять его вместе с Release Manifest. Для генерации рекомендуется Syft.
2. **Vulnerability scanning:** сканировать образы и зависимости до релиза; для начальной реализации рекомендуется Grype либо эквивалентный scanner. Результаты и исключения фиксируются.
3. **Image signatures:** собственные release images подписывать Cosign; для сторонних образов проверять подписи там, где поставщик публикует проверяемую подпись и известную identity.
4. **Digest verification:** запускать только образы с зафиксированным digest; проверка подписи не заменяет проверку digest.
5. **Provenance:** сохранять source commit, build workflow, builder identity и release metadata.
6. **License review:** сохранять сведения о лицензиях ключевых компонентов и проверять их перед релизом.
7. **Exception management:** уязвимости не игнорируются молча. Исключение содержит CVE/advisory, affected component, rationale, compensating controls, owner и review/expiry date.

Для локальной разработки подпись каждого временного образа может быть опциональной; для release candidate и воспроизводимых поставок собственные образы должны быть подписаны и проверены. Проверка сторонних подписей зависит от доступности и модели доверия поставщика; отсутствие подписи фиксируется как риск, а не автоматически трактуется как доказательство компрометации.

## 15. Runbooks и эксплуатационные процедуры

В репозитории должны храниться проверяемые runbooks:
- initial install/bootstrap;
- configure/validate/secrets decrypt;
- deploy/redeploy;
- upgrade each stateful component;
- rollback application/configuration;
- DB migration and recovery;
- PostgreSQL PITR + MinIO restore;
- restore/reconcile unfinished Temporal Workflows;
- rotate credentials and age keys;
- security advisory response;
- release verification and health checks.

Runbooks должны ссылаться на конкретные версии Compose/образов и быть протестированы на локальном окружении. Команды, способные удалить volumes или данные, должны иметь явное предупреждение и отдельное подтверждение.

## 16. Обновлённые открытые параметры и следующие решения

Не утверждены и требуют отдельного уточнения/PoC:
- конкретный стартовый режим LLM (внешний API или локальная модель) и provider/model; архитектурная поддержка обоих режимов подтверждена пользователем;
- конкретная версия Bifrost и результат security review;
- точные Compose network definitions, TLS между сервисами и механизм service identity;
- точный secrets bootstrap/rotation process;
- версии и topology Temporal self-hosted, namespaces, Web UI и migration process;
- bucket naming, retention и MinIO backup implementation;
- численные retention для logs/traces/metrics/audit/Langfuse;
- конкретные SLO/alert thresholds и нагрузочные лимиты;
- точные schemas и naming для config files, age key custody/rotation, CI provider и release registry;
- конкретные migration tools после выбора backend stack и Temporal deployment version;
- политики сроков хранения SBOM, scan reports, подписей и release artifacts;
- независимая backup storage для будущей production On-premises поставки;
- процедура и периодичность recovery drills.

## 17. Критерии готовности инфраструктурного MVP

### Дополнительные критерии конфигурации и обновлений

15. Все обязательные сервисы имеют зафиксированные tags и SHA-256 digests; в релизных Compose-файлах нет `latest`.
16. Конфигурация проходит schema validation и `docker compose config`; неизвестные/некорректные параметры приводят к ошибке.
17. Секреты в Git зашифрованы SOPS; age private key отсутствует в репозитории и хранится отдельно.
18. Renovate создаёт PR, но не выполняет автоматическое production-развёртывание.
19. Release Manifest позволяет определить точные образы, конфигурацию, миграции и версии правил конкретной поставки.
20. SBOM и результаты vulnerability scanning доступны для каждого собственного release image; собственные release images подписаны и проверяются.
21. Обновление проходит integration/compatibility tests и post-deploy health checks.
22. Проверен rollback приложения и конфигурации; для миграций документирована стратегия rollback/forward-fix/restore.
23. Recovery Manifest включает Release Manifest и конфигурационную версию.
24. Runbooks установки, обновления, отката, ротации секретов и восстановления проверены на локальном окружении.

1. AI RES запускается локально через Docker Compose без зависимости от Kubernetes.
2. API, Manager Runtime и общий Worker Runtime работают раздельно; длительные задачи не блокируют API.
3. Temporal сохраняет состояние и позволяет проверить cancellation/resume после перезапуска.
4. PostgreSQL разделяет `ai_res_db` и `temporal_db`; роли и миграции независимы.
5. MinIO хранит версии объектов, а PostgreSQL — их метаданные и ACL.
6. Redis можно не запускать без нарушения базовой функциональности.
7. Backup PostgreSQL и MinIO выполняется отдельно; восстановление проверено практическим тестом.
8. LLM Gateway Adapter отделяет AI RES от конкретного gateway; Bifrost PoC и security review пройдены до production-подобного использования.
9. Внешние обращения контролируются; секреты не попадают в контекст, логи и Workflow History.
10. OpenTelemetry traces связывают API → Manager → Temporal → Worker → LLM Gateway.
11. Доступны метрики, логи, traces, базовые dashboards и alerts.
12. Критические доменные действия фиксируются в отдельном Audit Log.
13. Для телеметрии и аудита применяются ACL, redaction и раздельные retention policies.
14. Восстановление БД/объектов и reconciliation незавершённых Workflow проверены по runbook.

## 18. Внешние технические источники

Использованы официальные материалы для выбора инструментов и проверки возможностей:
- Docker Compose production guidance: https://docs.docker.com/compose/how-tos/production/
- Renovate Docker/Compose updates and digest pinning: https://docs.renovatebot.com/docker/
- SOPS documentation: https://getsops.io/docs/
- Sigstore Cosign verification: https://docs.sigstore.dev/cosign/verifying/verify/
- Sigstore SBOM signing/attestation: https://docs.sigstore.dev/cosign/signing/other_types/

## 19. Связанные документы

- `AI_RES_Agent_Architecture_Concept_v3.5.md`
- `AI_RES_MVP_Capability_Matrix_v2.2.md`
- `AI_RES_Requirements_Lifecycle_v2.1.md`
- `AI_RES_Tool_Registry_and_Tool_Management_MVP_v0.2.md`
- `AI_RES_External_Integrations_and_Project_Context_v1.0.md`
- `AI_RES_Source_and_Context_Lifecycle_v1.1.md`
- `AI_RES_Documentation_Artifacts_Lifecycle_v1.0.md`


## 20. Связь с этапом 13 Security Architecture

Подробная модель угроз, идентификации/авторизации, секретов и проверяемых security controls вынесена в отдельные документы: `AI_RES_Security_Architecture_v1.0.md`, `AI_RES_Threat_Model_v1.0.md`, `AI_RES_Identity_Access_Control_v1.0.md`, `AI_RES_Secrets_and_Key_Management_v1.0.md`, `AI_RES_Security_Controls_and_Requirements_v1.0.md`. Предлагаемые там controls не становятся утверждёнными требованиями до отдельного согласования.


---

## Дополнение v1.3 — Authentication и Session Services

### MVP deployment
- Локальная аутентификация встроена в AI RES Backend; отдельный Keycloak/IdP не является обязательным контейнером или runtime dependency.
- Пользовательские credentials и server-side session records хранятся в `ai_res_db` с отдельными таблицами/схемой и минимальными DB grants.
- Redis остаётся optional и не является источником истины для sessions.
- Первый администратор создаётся одноразовой bootstrap-процедурой; default credentials запрещены.
- MFA TOTP secrets хранятся зашифрованными с ключом вне БД; recovery codes — только hash.
- Reverse Proxy завершает TLS; cookie `Secure` включён в HTTPS профиле. Backend проверяет CSRF token и Origin для cookie-authenticated state changes.

### Расширение внешним IdP
- `IdentityProvider` — внутренний порт; локальный provider входит в MVP.
- OIDC Adapter подключается позднее через Authorization Code + PKCE S256.
- OIDC issuer/discovery/JWKS endpoints задаются администратором и проходят allowlist/SSRF validation.
- OIDC не требует перестройки пользовательских memberships, RBAC, ACL или Policy Engine.
- SAML может быть предоставлен внешним broker, но прямой SAML SP не входит в MVP.

### Операционные требования
- Backup `ai_res_db` включает credentials hashes, identity mappings, session records и audit events; секреты TOTP и encryption keys защищаются отдельно согласно Secrets and Key Management.
- Restore/recovery должен обеспечить отзыв или принудительную ротацию активных сессий, если невозможно доказать целостность session state.
- Session revocation, password reset и account disable должны действовать на следующем API запросе, а не после истечения cookie.
- Auth endpoints включаются в rate limiting, security monitoring и audit.
- Нельзя писать password, reset token, session cookie, TOTP seed, OIDC authorization code, access/ID/refresh token или полный sensitive claims в logs/traces/Temporal history.

Подробная спецификация: `AI_RES_Authentication_and_Session_Management_v1.0.md`.


---

## Дополнение v1.4 — детализация Observability и operational requirements (Этап 14)

**Дата:** 2026-11-10  
**Основание:** `AI_RES_Observability_Architecture_v1.0.md`, `AI_RES_Monitoring_and_Alerting_Requirements_v1.0.md`, `AI_RES_Agent_Observability_and_Evaluation_v1.0.md`, `AI_RES_Operational_Runbooks_v1.0.md`.

### 10.8. Нормативные требования и границы стека
Состав стека из раздела 10.1 сохраняется: OTel SDK + Collector, Prometheus, Grafana, Loki, Tempo, Alertmanager/Grafana Alerting, отдельный PostgreSQL Audit Log; Langfuse остаётся optional Compose profile. Этап 14 не вводит второй параллельный observability backend. ELK, SigNoz, Phoenix, Sentry, PagerDuty и Evidently AI рассматриваются как альтернативы/дополнения только по обоснованной потребности.

### 10.9. Сквозная модель инструментации
Обязательный путь: API → Manager Runtime → Temporal → Worker Runtime/LangGraph → LLM Gateway → Tool/Connector. Инструментировать Readiness Gate, Context Builder/retrieval, Artifact generation/validation, Reviews/Approvals и recovery actions. Корреляция использует OTel trace context и доменные opaque IDs. Высококардинальные IDs остаются в logs/traces, не в Prometheus labels.

### 10.10. Разделение execution state, product quality и audit
Temporal остаётся источником durable execution state; AI RES domain DB — источником бизнес-состояния; operational telemetry — диагностической проекцией; Audit Log — отдельным источником значимых доменных/security событий. Execution success, `ACCEPTED_FOR_ORCHESTRATION`, verification, independent QA и human approval измеряются раздельно.

### 10.11. Поведение при отказе telemetry
Экспорт logs/metrics/traces не блокирует API/Workflow. Collector buffering/retry bounded; drop/export failures измеряются. Критические Audit Events не зависят от Collector; если обязательная audit запись не удалась, защищённое доменное действие не выполняется.

### 10.12. Privacy/access
Запрет по умолчанию на credentials, tokens, session secrets, full prompts/responses, documents, source fragments, code и confidential payloads. Redaction выполняется до backend. Access control применяется к dashboards, logs, traces и Langfuse с project/tenant isolation. Retention раздельный для metrics/logs/traces/LLM traces/feedback/audit. Численные сроки остаются OPEN до sizing/privacy review.

### 10.13. Dashboards и alerting
MVP dashboard inventory: Platform Overview; Temporal & Workflow; Manager & Workers; LLM & Tools; Product Quality; Telemetry Pipeline. Alert rule обязан иметь severity, scope, condition/window, owner, runbook, user impact, auto_action и silence policy. Alert не имеет полномочий менять права, approve/publish артефакты, переключать модель или удалять данные.

### 10.14. Agent feedback и evaluation
Production traces являются кандидатами в Evaluation Set только после sanitization, review и проверки прав. User feedback не запускает автоматическое обучение. Drift alert инициирует анализ, но не автономное fine-tuning/retraining. Shadow runs должны исключать side effects; canary не является требованием для локального single-node MVP.

### 10.15. Runbooks
Операционные сценарии и процедуры этапа 14 вынесены в `AI_RES_Operational_Runbooks_v1.0.md`. Runbooks являются проектными процедурами; их фактическое тестирование на развернутом окружении остаётся обязательным implementation gate.

### 10.16. Критерии observability readiness
1. Сквозная trace связывает API, Manager, Temporal, Worker, LLM Gateway и tools.
2. Есть dashboards по шести областям из 10.13.
3. Проверены redaction и межпроектная изоляция.
4. Проверен fail-open telemetry и bounded buffering.
5. Audit Log отделён и проверена реакция на его отказ.
6. Критичные alerts имеют owners и runbooks.
7. Проверены сценарии Temporal backlog, provider outage, tool failure, telemetry outage, storage pressure, data leak и rollback.
8. Langfuse отключается без влияния на core workflow.

### 10.17. Открытые параметры
Численные SLO/SLI targets и alert thresholds; retention и storage sizing; alert destinations/on-call; Langfuse activation/content capture; drift feature set/thresholds; точные OTel exporter versions и coverage. Эти параметры нельзя считать утверждёнными только на основании данного документа.


---

## Дополнение v1.5 — Performance, Scalability & Resilience (Этап 15)

### 11.1. Модель нагрузки
Нагрузка AI RES классифицируется по интерактивным API, Manager planning, Worker execution, ingestion, artifact generation, traceability/impact, QA/evaluation, observability и backup/recovery. Нельзя оценивать capacity только по HTTP RPS.

### 11.2. Изоляция и admission control
- API/control plane изолируется от фоновых Worker, ingestion и evaluation workloads.
- Общий Worker Runtime pool получает глобальные и capability/task-class concurrency limits.
- Устанавливаются quotas/budgets по organization/project/task, LLM tokens/cost, tool calls, wall-clock time, context/output size.
- Backpressure ограничивает admission и queue growth; UI/API показывают queued/throttled/blocked/rejected state с reason.
- Приоритеты не должны допускать starvation; численные классы/aging OPEN.

### 11.3. Масштабирование
Stateless API и Runtime допускают горизонтальное масштабирование после проверки shared state, idempotency and concurrency. Worker Runtime — основной scale-out axis. Manager Runtime масштабируется с учётом сериализации/optimistic concurrency на Epic/Plan. PostgreSQL, Temporal persistence и MinIO требуют отдельного stateful scaling/HA design; увеличение числа контейнеров само по себе не обеспечивает HA.

### 11.4. Data and connection management
- DB connection budget учитывает все API/Manager/Worker/Temporal/maintenance processes.
- Query tuning/indexing основаны на измерениях; списки имеют bounded pagination; bulk work асинхронен.
- Большие payloads и документы не помещаются в Temporal history; передаются object/version refs.
- Cache требует ACL-aware keys, version invalidation and TTL; не является source of truth.
- Большие файлы/артефакты обрабатываются с ограничением памяти и размера.

### 11.5. Resilience patterns
Bounded retries with backoff/jitter, timeouts, cancellation propagation, circuit breakers, bulkheads, idempotency, deduplication, transactional outbox/inbox, checkpointing, compensation/reconciliation and graceful degradation применяются по типу операции. Exactly-once external side effects не обещается.

### 11.6. Failure behavior
- LLM/tool outage: bounded retries, approved fallback или explicit blocked/waiting.
- Worker/Manager restart: durable Temporal state and safe retry.
- Temporal unavailable: не подтверждать durable start.
- PostgreSQL unavailable: protected domain mutations fail closed.
- MinIO unavailable: operations requiring object bytes fail safely; не создавать dangling references.
- OTel/Langfuse/Redis optional outage: core workflow continues subject to audit/security constraints.
- Audit write failure: protected mutation не commit.
- Saturation/disk pressure: backpressure and degraded mode; canonical data не удалять.

### 11.7. Recovery and HA
Существующие цели RPO ≤ 1h / RTO ≤ 4h остаются целями до подтверждения drills. Production On-prem requires independent backup storage, Recovery Manifest, restore drills and reconciliation Domain DB ↔ Temporal ↔ MinIO ↔ external side effects. Single-node Compose MVP не обеспечивает node-level HA. HA topology проектируется отдельно.

### 11.8. SLO and capacity
Численные latency/throughput/concurrency targets не утверждаются без baseline. Для critical journeys определить SLI/SLO, measurement window, owner, alert and error budget. Async workflows измеряются отдельно по task class, включая queue wait, time-to-start and execution duration. Capacity model учитывает пользователей, проекты, Worker Runs, ingestion, LLM/provider quotas, DB/IOPS, MinIO, telemetry and backup throughput.

### 11.9. Load and resilience testing
Обязательные типы: baseline, load, stress, spike, soak, capacity, resilience-under-load and recovery. Нагрузочные сценарии включают Workspace, planning, mixed Worker pool, ingestion, artifact generation, impact analysis, QA, provider degradation, Runtime restart, Temporal restart, DB/MinIO pressure and optional telemetry/cache outage.

### 11.10. Связанные документы
- `AI_RES_Performance_Scalability_Resilience_Architecture_v1.0.md`
- `AI_RES_Performance_Scalability_Resilience_Requirements_v1.0.md`
- `AI_RES_Resilience_and_Recovery_Requirements_v1.0.md`
- `AI_RES_Capacity_and_Load_Test_Plan_v1.0.md`

### 11.11. Open items
Численные SLO/capacity, concurrency and queue limits, priority/fairness, connection pooler, production HA topology, provider fallback matrix, retry/circuit-breaker parameters, retention/storage sizing and measured RPO/RTO remain OPEN until baseline and validation.


---

## Дополнение 1.6 — PostgreSQL migration operations и role isolation

**Нормативное решение:** для `ai_res_db` применяется Alembic + SQLAlchemy 2.x; migration execution отделён от runtime. Используется expand → backfill/migrate → validate → contract. Alembic autogenerate создаёт только candidate migrations и всегда требует ручного review. Temporal и LangGraph persistence мигрируются отдельными владельцами.

PostgreSQL access разделяется по process identity: `ai_res_owner` (NOLOGIN), отдельный `ai_res_migrator`, `ai_res_api`, `ai_res_outbox_dispatcher`, `ai_res_event_consumer`, `ai_res_auditor` и backup identity. Manager Runtime и Worker Runtime не получают прямые DB credentials. Runtime роли не имеют DDL, object ownership, SUPERUSER, BYPASSRLS или доступа к owner role.

RLS + FORCE применяется к tenant/project scoped таблицам; transaction-local `app.organization_id`/`app.project_id` устанавливаются только после серверной авторизации. Отсутствующий контекст — default deny. RLS является defense-in-depth и не заменяет Policy & Permission Engine; GUC-based policies не защищают от произвольного SQL под скомпрометированной общей API identity. Все query/retrieval/export/cache/event paths сохраняют объектную ACL-проверку.

Подробная стратегия, роли, политики, миграционный runbook и acceptance criteria — `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.0.md`; SQL reference — `AI_RES_PostgreSQL_Roles_RLS_v1.0.sql`. Реальное внедрение и runtime tests не заявляются.

Alembic deployment job выполняется как отдельный one-shot deployment task с migration credential, а не при старте API/Runtime. `pg_hba.conf` ограничивает подключения; сетевой доступ к PostgreSQL доступен только backend/maintenance network. TLS + SCRAM-SHA-256 обязательны для сетевых соединений; credentials provisioned и ротируются через Secret Manager. `ai_res_migrator` активируется на время deployment; backup identity отделена от runtime.


## Дополнение v1.7 — Persistence implementation pipeline

Для `ai_res_db` применяется единый Alembic environment с version table `platform.alembic_version`, allowlist доменных схем и отдельным one-shot deployment job. API/Manager/Worker startup не выполняет DDL. Migration job использует отдельный временно активируемый `ai_res_migrator`; application identities не получают DDL.

Deployment pipeline включает revision graph/single-head check, schema drift, preflight (server version, locks, long transactions, disk/backup), migration, resumable backfill, constraint/RLS/grants validation, postflight и release evidence. Production contract migration требует restore rehearsal и подтверждённого Recovery Manifest. Полный порядок и DoD — `AI_RES_Persistence_Implementation_Blueprint_v1.0.md`.
