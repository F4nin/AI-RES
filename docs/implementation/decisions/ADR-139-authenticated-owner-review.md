# ADR-139 — authenticated owner identity-review material

**Дата:** 2026-11-18. **Статус:** ACCEPTED technical scope в порученной подготовке
G156; локальное evidence в [отчёте](../increments/G02_owner_review_binding_REPORT.md).
Полный G156 NOT VERIFIED, G02/S17/S20/S21 NOT_STARTED.

## Основание

DOC076 v1.1 §3.1/7 требует отдельную человеческую приёмку exact observed identity.
IAM v1.5 §8 требует exact version/hash. Решение владельца в DECISIONS_PENDING,
«Дополнение к OD-01 / OD-21» (2026-11-14): профиль и Bifrost/security утверждает
лично владелец через CLI/API с аудитом, второй человек не требуется. ADR132
запрещает выводить global authority из ORGANIZATION_OWNER любого tenant.

## Решение и точный scope

Подготовить backend-only материал identity review и повторно вычислять его при
сравнении с предыдущим. Это самостоятельный preparatory seam, не approval command.
В `OwnerReviewService` доверенная composition явно задаёт exact organization/user/
profile. Отсутствие binding даёт deny. Action `model_admission.review` дополнительно
проверяется через существующий PolicyEnforcer; packaged policy не меняется и
продолжает отказывать. Positive grants существуют только в synthetic tests.

Две короткие UoW: живые subject/session/MFA факты; Policy вне транзакции; затем
повтор subject под SHARE locks, ADR138 fence перед profile/control и полный снимок.
Порядок locks membership/user → active MFA factor → session согласован с existing
MFA reset/verify (factor → session). После ожиданий вновь проверяются live session,
subject и scheduled profile deprecation. Результат audit failure не возвращается.
Обычная audit запись POLICY_DECISION относится к реальному authenticated subject
в его организации; это не global admission APPROVED/owner lifecycle audit.

Один canonical parsed observation хешируется и сравнивается с evidenceSha256
предлагаемого expectation. Identity/managed refs должны совпадать. Существующий
contract0.2 не меняется; это дополнительная проверка его потребителя. Digest не
доказывает происхождение observation, live capability либо Bifrost §7 acceptance.

Binding0.1 включает exact human/session/subject/MFA, action/policy version,
expectation и observation hashes, полный фактический profile snapshot, control,
active-generation record и pending receipts. Предлагаемая generation ровно current+1
(для отсутствующего control —1). PostgreSQL JSON text хешируется как непрозрачная
строка: numeric не проходит через Python float. TimeZone/JSON rendering DB входят
в техническое окружение; иной rendering может безопасно инвалидировать review.

`previous` — сравнение заново прочитанных фактов, без сохранённого permission или
replay shortcut. Изменённые actor/session/policy/profile/control/pending/evidence
инвалидируют материал. Pending/block не очищаются. Read-only review разрешает
увидеть наличие pending; executor не получает из этого разрешение снять barrier.

## Границы

Нет approval/lifecycle DML, migrations/grants, нового endpoint/CLI, реального owner
binding, profile/approval/key seeds или модельных calls. API не получает owner/
migrator factory либо migration_mode. Existing pinned loader/factory/transport
guards сохраняются. Fence вынесен в shared helper без изменения прежнего SQL.

Материал не является authenticated human decision, capability или проверкой
полного Bifrost acceptance manifest. Будущий narrowly privileged operator executor
обязан самостоятельно authenticate/authorize/revalidate и атомарно audit exact
decision/version/generation, сохраняя unresolved receipts. Ни один consumer сейчас
не использует OwnerReview для approval/dispatch. Точные live identity, data/egress,
бюджет и отдельные human acceptance остаются до включения.

Проверки времени выполняются до policy audit; истечение во время самого audit/commit
не объявляется физически невозможным. Это особенно не даёт permission для будущего
действия после возврата материала. No exactly-once/TTL/autoclear/retry обещаний.

## Проверка

Real PostgreSQL16/API role: exact/wrong/absent human, stale sessions/MFA/member/user,
Policy deny/unknown/outage/timeout/approval-required, audit outage, exact hashes,
generation/block/pending/lifecycle, replacement session/policy, actual fence wait
expiry, factor-first reset interleave и lossless numeric snapshot. Старые guard/
lifecycle tests проверяют извлечение helper. Independent general/Python/database
и security reviews обязательны. Full G156/pre-pr/Linux CI/live/SLICE остаются gates
общей подготовки; этот локальный checkpoint не повышает продуктовый статус.
