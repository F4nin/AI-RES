# ADR127 — независимая проверка группового процесса

**Дата:** 2026-11-17. Прямое поручение владельца в ходе G01: сначала реализовать этапы группы, затем общая отладка и проверки. Reviewer `/root/s19_review` не автор редакции; read-only, сначала process diff/источники без авторского отчёта. ECC code-reviewer/doc consistency checklist применены отдельным reviewer; native Claude commands/hooks не запускались.

Scope:15Markdown-файлов — AGENTS§3/§11, DEVELOPMENT_GROUPS§1/§3 и исторические sections, ADR124/127/решения, roadmap§5, retention/template/tooling/index/status, shared context/evidence. Product source/CI/Makefile не меняются; первоначальные group-governance hunks входят в новое явно порученное уточнение.

Найденная неоднозначность: «все внешние зависимости DONE» могла запрещать ранний независимый S35 до будущего S31, нужного только S36. Исправлено: внешняя предпосылка нужна перед соответствующим зависимым Sxx; внутренние контракты реализуются по DAG в одной ветке, без промежуточного обязательного merge. Поздняя внешняя зависимость не блокирует независимую раннюю часть.

**Final APPROVE, open findings0.** Подтверждены единый групповой цикл и один PR, сохранённые Sxx scope/DAG/reports/traceability/status evidence, отсутствие обязательного per-stage полного pre-pr/CI/review/PR, общие final gates с явным покрытием и нужными независимыми компетенциями. Product Readiness Gate, human/security approvals, permissions, бюджеты и release ограничения сохранены; одиночный режим не изменён.

Reviewer:176локальныхMarkdownссылок/0missing,gitdiffcheckPASS; никаких правок/БД/runtime/test runs. Root:40prompts/0issues,8groups/23stages/0missingduplicates,composition diff0,secret scan0,producttree diff0 vs7dd8475. Эти проверки документов не объявляются runtime verification; S18 source/final-stage Linux evidence уже имеет отдельные точные SHA/runs.

Новая summary-запись этого review не добавляет новых правил; финальные ссылки/diff/secret scan проверяются перед process commit. Точный finalhead/CI/merge публикуется в PR33, без self-referential SHA в собственном commit.
