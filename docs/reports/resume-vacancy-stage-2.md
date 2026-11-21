# Resume → vacancies · stage 2 implementation

21 November 2026. Branch `codex/resume-vacancy-stage-2`, base `deed93a`. Decision: headquarters ADR-009, variant C. No comparison benchmark was requested; model quality or cost improvement is not claimed.

## Implemented

Authenticated HR can upload a TXT/DOCX/text PDF without an application, process current vacancies, inspect source-grounded assertions, correct extracted facts or register a new redacted text version, and reread a dated result. Identical successful stages reuse persisted artifacts. Existing assessment arithmetic/evidence validation is retained; formal requirements and competency indicators use independently reusable semantic checks. Existing HR-confirmed assessments are not overwritten. Candidate decisions remain separate.

The default catalog is the actual legacy Vacancy table. Optional Requirements HTTP reader uses version/content/organization-checked bindings; unmapped profiles remain explicitly unresolved. Runtime integration with the external Requirements deployment has not been exercised; controlled transport tests cover its response and outage boundary. No profile is generated from a vacancy title.

Yandex configuration remains the product default. Local Gemini 3.5 Flash uses an ignored env file excluded from Docker context. No credential is in the delivery. Yandex calls were not repeated in this task to preserve its token budget.

## Checks performed

Before publication, merged current main `e243e2f` including David's interaction window. Resolved the revision collision by moving this migration to **0015 after 0014**. A fresh isolated PostgreSQL run applied both migrations and passed **54 targeted tests in 12.57 s** (resume chain, matching, artifact storage, evaluator, catalog adapter and LLM client). No new live model requests were made for this integration check.

- PostgreSQL 16 + pgvector: migration 0015 applied through the complete migration chain on a new dedicated database. No existing database was dropped.
- 37 targeted PostgreSQL checks passed in 7.39 s: new chain, previous matching behavior, artifact storage and existing assessment service.
- After adding the provider-outage regression: both HTTP-chain variants passed in 5.16 s, including preservation of extraction on retry, fact correction, source-text invalidation, closed-vacancy/empty-catalog handling and run rereading.
- 62 targeted provider/artifact/rule/evidence tests passed earlier; 4 artifact/catalog boundary tests passed in 0.87 s. These batches overlap and are not added into a fictitious total.
- A real uvicorn HTTP run using Gemini 3.5 Flash passed upload/repeat, live catalog assessment, repeat without a new assessment, department 403, fact correction/stale 409 and evidence rereading after restart. Inputs are synthetic, based on the existing py-9001 assessment fixture; six catalog entries were scanned.
- Gemini also returned transient connection/server failures in subsequent attempts. The command now returns 503 PROCESSING_UNAVAILABLE and persists successful stages; this behavior is covered by the targeted regression. Failures do not become an empty successful recommendation.
- The final live rerun did **not** pass: Gemini 3.5 Flash returned HTTP 503 on FormalExtraction after bounded retries. Further provider retries were stopped. Thus the earlier successful real HTTP path and the final controlled PostgreSQL tests are separate evidence; final live model availability is not claimed. The final provider/catalog/artifact batch passed 18 tests in 3.94 s.

Commands: `python -m scripts.check_resume_vacancy_chain --env-file <ignored-local-env>`; `pytest tests/test_resume_chain.py tests/test_matching_vacancies.py tests/test_processing_artifacts.py tests/test_assessment_service.py -q`. Database tests require a dedicated TEST_DATABASE_URL ending `_test` as in the repository's existing rules. The live script stores its summary and server log only in `deploy/local`.

## Limits

This is a server/API delivery, not connected UI. OCR is not implemented: unreadable/scan pages return needs_review. External profile mappings require the owner's verification; the adapter does not infer equivalence. Existing legacy staff/single-organization gateway access remains the deployment boundary. Per-model real quality, production load, external Requirements integration, crash-after-provider-execution exactly-once behavior and frontend rendering were not verified. Original files require a persistent HR_RESUME_FILES directory.

The shared product checkout contains this branch's changes. No production deployment is performed by these checks.
