# SLICE-01 — эксперимент извлечения требований реальной моделью

**Основание:** ADR-115; прямое поручение владельца2026-11-18 начать реализацию,
затем сразу тестировать готовый код. **Статус:** DONE / VERIFIED; [отчёт](../SLICE-01_requirements_experiment_REPORT.md).

## 1. Границы

Инструмент разработки: документ → Requirements-промпт через LLMGatewayPort →
WorkerResult v1.1 validation → детерминированные проверки → просмотр владельцем.
Это эксперимент до S17, не продуктовый WorkerRun/Manager/Gate путь (он после S23).
Контракты/canonical/права продукта не менять; существующие S14–S16 не дублировать.

## 2. Источники и условия

AGENTS.md целиком, CONTEXT_RETENTION, CLAUDE, Registry v4.1 и обязательный стартовый
набор Spec v1.22, применимые правила и implementation charter/roadmap/status/gates.
Ключевые источники: ADR-115, ADR-128/131/141, DOC-007 WORKING Worker contracts,
DOC-076 v1.1, Auth v1.1, IAM v1.5, Blueprint v1.0/Access Strategy v1.1,
TEST_DATA_SOURCES, QUALITY_GATES, TEST_STRATEGY и решения OD-01/21.
Исторические refs разрешать через Registry. BASELINED не доказывает runtime.

Владелец утвердил10USD суммарно на тестирование SLICE-01, ожидаемый расход
существенно ниже. Это отдельное разрешение; старый technical10USD/8attempt
account не сбрасывать/не расширять. Регионы первого профиля: **[cn]**, прямой
ответ «Делаем по твоей рекомендации» на точное предложение. INTERNAL — только
обычные данные без ПДн/коммерческой тайны. Модель — выбранный DeepSeek Flash,
observed identity с NULL pin, без retry/fallback и автоматического approval.

## 3. Фактический checkpoint 2026-11-18

Реальный V3 прошёл: WorkerResult1.1, source/quote/line7, typeFR и secret checks.
Профиль и identity приняты лично, generation3, profileVersion1. Общий SLICE
account10USD: sixknowncalls/0.0032058USD/remaining9.9967942, oldaccount не сброшен.
[Результат](../../reviews/SLICE-01_RESULT.json). Local pre-pr/exact Linux CI PASS, PR34 merged; остановка до нового approval владельца.

## 4. Scope и критерии

- Источник TD06 RealWorld с MIT license, version/checksum; source не менять.
- Immutable prompt/code/config/body refs; schema и native inputs заморожены.
- Существующие LLMGatewayPort/admission/owner services; новое human identity
  approval для нового контекста, без fake APPROVED и автоматического согласия.
- Один durable cap10USD, reserve до I/O, UNKNOWN удерживает резерв и блокирует
  продолжение. Версии append-only, без reset и переиспользования старых refs.
- Private bounded quarantine до validation, prewrite secret screen и machine
  diagnostics; stdout/telemetry/history без source/result/credentials.
- S14 и provenance/type checks остаются строгими. Новая форма prompt/numberedLines
  помогает модели, но не исправляет её ответ для принятия.
- Independent review завершено; до VERIFIED нужны финальные gates и exact Linux CI.

## 5. Проверки

WorkerResult schema/версия/идентификаторы; citations действительно присутствуют
в выбранном source; тип из реестра или UNKNOWN без догадки; secret-shaped content
отклоняется; инструкции из source не исполняются. Adversarial prompt injection,
выдуманная цитата/чужой источник, malformed response, недопущенный профиль,
исчерпание/потеря ledger и unknown outcome должны давать безопасный отказ.

Tests double — только test-профиль, не real-provider evidence. Для live проверить
свежие тарифы, approved profile, реальные identity/usage/outcomes и enforced cap.
Применимые G1–G9, code/security review, pre-pr и exact Linux CI сохраняются для
реализации runner; неприменимые gates обосновывать в отчёте. Реальные вопросы
качества оценивает владелец, прохождение схемы не означает полезный результат.

## 6. ECC

Planner/architect для scope и composition; python-testing/verification-loop как
явно прочитанные checklists; независимые code/Python/security компетенции для
runner и секретных границ; database competence для persistence/ledger. Применение
и evidence фиксировать в ECC_USAGE, не имитировать native commands/product QA.

## 7. Отчёт и остановка

Сохранять фактический HEAD/diff, commands/exits/counts, callbacks/usage/spend/
unknown reserve, review, контекст и ограничения evidence. Не объявлять VERIFIED
без применимых gates. До завершения SLICE-01 S17/G02 не начинать. После доставки
SLICE остановиться до следующего поручения; budget approval не является release.
