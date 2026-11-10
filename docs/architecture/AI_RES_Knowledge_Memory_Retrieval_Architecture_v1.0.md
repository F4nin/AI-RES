# AI RES — Knowledge, Memory и Retrieval Architecture

**Версия:** 1.0 | **Статус:** BASELINED.

## 1. Цель и разграничение

Source of Truth, Project Knowledge, Episodic Memory, Semantic Experience Memory и Working Context — разные категории. Ни одна запись памяти не является разрешением на доступ или заменой утверждённого доменного объекта.

## 2. Хранение MVP

- PostgreSQL: source metadata/version, ACL, provenance, fragments, extracted assertions, relationships, index metadata, embeddings (`pgvector`), FTS (`tsvector`/GIN).
- MinIO: originals, immutable source payloads, large extracted artifacts and snapshots.
- Redis: cache/ephemeral coordination only.
- No separate vector DB or graph DB in MVP. Graph is logical relational model; GraphRAG deferred until benchmark proves need.

## 3. Ingestion

Receive → malware/type validation → immutable object storage → parse/OCR → normalize → fragment with locators → classify/sanitize → ACL/provenance attach → lexical/vector index generation → extraction of assertions/candidates → validation → publish index generation. Each step is versioned and resumable. Failed parse never silently replaces previous valid SourceVersion.

## 4. Retrieval

Query understanding → authorization scope → lexical + dense candidate retrieval → ACL filter (before ranking and context assembly) → deduplicate/merge → optional rerank authorized candidates → freshness/authority weighting → evidence pack → Context Builder. Return source/version/fragment refs, offsets, scores, freshness, authority, limitations and ACL decision metadata.

## 5. Context engineering

ContextPackageVersion is immutable and binds source versions, memory refs, ruleset, retrieval query/strategy, model/embedding versions, selected fragments, truncation decisions and content hash. WorkerRun stores exact package ID/hash. Summaries preserve provenance and cannot expose inaccessible source text.

## 6. Memory write policy

Workers may propose memory candidates. Promotion to shared project knowledge or semantic experience memory requires deterministic validation and/or human/Manager review according to type and risk. No automatic cross-tenant or cross-project promotion. Personalization memory is scoped to user and cannot override project/system rules.

## 7. Update and deletion

Source change creates new SourceVersion and index generation; previous versions remain addressable according to retention. ACL revocation invalidates retrieval/cache access immediately. Deletion workflow covers object store, database metadata, vector rows, FTS, caches, derived summaries and backup expiry/legal hold. Deletion is auditable; backups are not selectively rewritten unless policy requires it.

## 8. Retrieval evaluation

Per task class measure Recall@k, Precision@k, MRR/nDCG where labeled data exists, evidence coverage, stale-result rate, ACL leakage (must be zero), citation correctness, latency and token cost. Build sanitized golden queries and hard negatives. Embedding/model change creates new index generation and benchmark comparison; rollback restores prior generation.

## 9. MVP boundary

Hybrid PostgreSQL FTS + pgvector; immutable sources/context; project-scoped retrieval; ACL-before-context; citations/provenance; no GraphRAG, no independent vector service, no automatic semantic learning.
