# S16 — независимые review отключённой интеграции

**Дата:** 2026-11-17. Scope: новый HTTP/SSE transport, relay, budget seam, renderer/config/catalogs, Compose/policy/dev credentials и Make/CI/probe. Это review реализованного среза, не human acceptance Bifrost/model и не завершение S16.

Исходные planner/architect/security выводы pinning sub-PoC — [отдельно](S16_PREFLIGHT_REVIEWS.md). Затем по поручению владельца независимая реализация продолжена. Нормативное исключение NCP-16 не одобрялось.

## Независимость и фактический способ

| Проверяющий | Применённые ECC роли | Охват / исключения |
|---|---|---|
| `s16_security` | security-reviewer + silent-failure-hunter | Весь кодовый срез; не писал его. Blind-first до авторского implementation report. Повторно проверил исправления Unicode и no-paid guard |
| `s16_arch` | code-reviewer + python-reviewer + pr-test-analyzer | Adapter/tests, renderer/config, root Compose/checker/secrets/Make/CI. Исключил собственные relay/gateway. Первоначальная in-flight pricing/auth дельта отдельно отмечена |
| `s16_docs_review` | code-reviewer + python-reviewer + pr-test-analyzer | Relay/gateway/errors/tests, root Compose/checker/secrets/Make/CI/probe/supply-chain, renderer/catalogs. Исключил собственный adapter |
| `s16_plan` | tdd-guide | Ретроспективное test-design/mutation review adapter/relay/budget/probe/checker, исключил собственный renderer/catalog. Мутации только в памяти отдельного процесса |

Новую отдельную thread для общего review создать не удалось: harness вернул thread limit. Компенсация — имеющиеся отдельные агенты проверяют чужие файлы, собственные исключены; security reviewer независимо покрывает всё. Самопроверка не выдана за независимое review. Нативные Claude slash commands/hooks не запускались.

## Findings и исправления

| Серьёзность | Evidence / trigger | Исправление / проверка |
|---|---|---|
| MEDIUM | Provider JSON с unpaired surrogate проходил JSON Schema либо вызывал raw UnicodeEncodeError в tool arguments/relay response; stream терял typed semantics | `_json`/`_loads` валидируют UTF-8 scalars до forwarding/output; tool fragment bytes учитываются инкрементально. Tools2RED и content/relay4RED зафиксированы, затем целевые202passed. Security delta подтверждён |
| MEDIUM | Первоначальный no-paid probe отправлял authenticated model-shaped request до проверки disabled relay. При ошибочно live target мог бы потратить бюджет | Host exact command/env/mount preflight, затем disabled health до всех model-shaped requests; live/unknown modes останавливаются. Четыре поведенческих probe guard tests и мутации guard/command обнаружены. Security delta подтверждён |

Текущие подтверждённые открытые findings отключённого среза: **CRITICAL0/HIGH0/MEDIUM0/LOW0** по итоговым сообщениям reviewers. Отсутствие public immutable selector — известное owner-условие NCP-16/G-156, а не незаявленная уязвимость включённого продукта; real routing остаётся закрытым.

## Проверки reviewers

- Reciprocal reviewer лично выполнил backend relay+gateway122passed и infra renderer/policy/checker114passed с `-B -p no:cacheprovider`; diff check PASS. Остальные reviewer не запускали runtime/контейнеры, не читали реальные secret values, не делали paid calls.
- TDD-guide обнаружил4/4 мутации: API в llm_upstream, удаление exact gateway networks, обход disabled-health guard, обход host command guard. Shared source files не менялись. Это чувствительность проверок, не доказательство первоначальной RED-хронологии.
- Реальные Docker/Bifrost проверки и полный pre-pr выполняет основной исполнитель; evidence — report. Их не приписываем reviewers.

## Пределы review

Условие immutable pinning, реальная provider compatibility/feature mapping, stage-wide durable billing cap и human acceptance не доказаны fixtures. Secret-free admin/VK runtime и network isolation относятся к отключённому PoC. Тарифы локального каталога — operator metadata, не invoice/approval. До live testing нужно закрыть условия [плана](S16_PAID_TEST_PLAN.md), не обходя CANDIDATE/approval. Полный stage status остаётся ниже VERIFIED.

## Owner closeout — последующее документационное review, 2026-11-17

Владелец прямо поручил закрыть технический milestone S16 по основному механизму LLM Gateway/подключения провайдеров. ADR-123 фиксирует DONE по owner decision, сохраняя TESTED evidence и NOT VERIFIED реального provider path.

Отдельный `s16_security` read-only: blind-first оценка scope/approval границ до авторской дельты, затем actual review14Markdown относительно288be77 и delta recheck. Обнаружен один MEDIUM: ROADMAP S34/S39 и цвет/подпись S16 продолжали обозначать закрытый технический этап как blocker. Исправлены причины блокировок и caption/color, edges/dependencies/очередь не менялись. Финальный verdict **APPROVE, open CRITICAL0/HIGH0/MEDIUM0/LOW0**, diff check exit0. Собственных правок, runtime/paid calls и чтения secret values reviewer не выполнял.

Проверены: точечное owner-уточнение ADR-032, сохранение исходного невыполненного DoD в report§17, NCP-16 PROPOSED, отсутствие claims real-provider VERIFIED/APPROVED profile/Bifrost ACCEPT, сохранение live/SLICE/release gates. После verdict добавлены только этот протокол и точные результаты docs checks; это не новое runtime/security approval продукта.
