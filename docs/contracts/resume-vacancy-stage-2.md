# Resume → vacancies · stage 2

Decision: headquarters ADR-009. Owner: recruitment. Computational components remain inside legacy for this transition; no new microservice is introduced. Yandex remains the default LLM provider. All routes require the active HR/admin context of the existing API; working contour also requires the server search credential. This is the existing single-organization training/gateway boundary, not a new public candidate endpoint.

## Commands

Paths are relative to `/api/v1/matching`.

| Route | Input / result |
|---|---|
| `POST /resumes` | `{filename,content_base64,contour}`; TXT/DOCX/text PDF up to 8 MiB. Saves original and redacted candidate text without Application. Same bytes return same candidate; opposite contour is 409. Unreadable/scan or failed redaction returns `needs_review`, document ID and reason, never a qualification verdict. |
| `POST /vacancies/current/process` | `{candidate_id,contour,limit:1..50}`; explicit LLM-capable command. Reads current catalog, evaluates unique mapped profiles, returns result, facts_id, processed/reused profile IDs, confirmation_review_required, run_id and catalog_count. |
| `POST /vacancies/process` | Existing `VacanciesForCandidateIn` with provided snapshots; explicit processing, same assessment rules. |
| `GET /runs/{run_id}` | Immutable dated result; `is_snapshot=true`, `source_is_current` checks the candidate text only. Publication/action availability must be checked at action time. |
| `GET /resumes/{id}/facts/{facts_id}` | Source-specific assertions with exact Evidence offsets, limits and extraction/HR-correction provenance. |
| `POST /resumes/{id}/facts/correct` | `{expected_facts_id,contour,reason,corrected:{card,assertions,limitations}}`; assertions use kind,statement,quote,context_before,polarity. Quotes must exist in the source. New effective version, no original rewrite or LLM extraction. Concurrent/stale correction: 409. This corrects extraction, not formal eligibility. |
| `POST /resumes/{id}/text` | `{expected_text_id,text,reason,contour}`; HR registers a new redacted text version with audit/provenance. Old source/evidence retained. New text invalidates extraction. Stale version: 409. |

Existing `POST /vacancies` remains read-only. No matching command creates an application or moves a candidate stage. HR-confirmed Assessment is not replaced by a model: profile is returned in confirmation_review_required.

`coverage=complete` means all entries of the catalog snapshot were visited. `evaluation_complete=false` means unmapped/unassessed profiles or confirmation review remain. Unknown qualification is a valid evaluated outcome; it is not a technical failure. `limit` truncates displayed evaluated items, not the catalog traversal. `needs_evaluation` remains explicit. Provider failure returns 503 PROCESSING_UNAVAILABLE and preserves completed stages; it never returns a false empty successful match.

## Catalog and profile boundary

Default source is the real open Vacancy table (`source_mode=legacy_catalog`), grouped against current approved profiles of the requested contour. Legacy has no publication revision column; snapshot revision 1 is an adapter marker, and the snapshot timestamp/profile version identify the observed state.

To use Requirements, set server-only `HR_MATCHING_CATALOG_URL`, `HR_MATCHING_CATALOG_TOKEN`, and optional `HR_MATCHING_PROFILE_MAP` path. Reader uses `/api/v1/catalog/vacancies?status=published` and `/api/v1/profiles/{id}`. Unavailable source returns 503, not empty data. Do not expose the token to the browser.

The binding JSON is a list with `catalog_profile_id`, `catalog_version`, `organization_id`, `contour`, `catalog_content_hash`, `legacy_profile_id`, `legacy_content_hash`. Hashes are canonical fingerprints from `app.assessment.artifacts.fingerprint`; legacy hash uses `profile_manifest`. The owner verifies semantic equivalence before supplying a binding. Current status, organization, contour, exact version and both content hashes are checked on each read. Missing/stale binding produces needs_evaluation/unmapped_profile. There is no automatic profile generation or approval from a vacancy title.

## Storage, reuse and errors

Migration 0014 adds immutable processing_artifacts. Source record/contour is part of every key. Extraction key includes source version/content, extractor configuration and schema. HR corrections create effective facts IDs. Semantic checks include effective facts, prompt, model/provider/configuration, exact query and schema. Formal requirements and competency indicators are checked separately; deterministic numeric calculations keep the existing code. The original text remains a fallback, so omissions in extraction cannot become mandatory negative filters.

Model failures/invalid schemas do not become cached unknown. Grounding errors reject extraction. A candidate row lock serializes processing/corrections for that source; unique artifact keys prevent duplicate accepted records. This does not promise exactly one paid call across a crash. Old successful stages survive a provider error. No external LLM call is performed on a fully cached repeat.

Original files default to `data/resume-originals`, configurable with `HR_RESUME_FILES`; supplied filenames never determine server paths. This directory must be persistent in deployment and is not a static web directory. No API exposes arbitrary file paths. OCR is not implemented: scans explicitly require review. The authenticated HR may record a corrected source text; this is not claimed as OCR.

## Verification

`python -m scripts.check_resume_vacancy_chain --env-file <local-env>` requires a dedicated PostgreSQL database ending `_test`, applies migrations, uses the existing synthetic assessment fixture and actual HTTP/server restart. The chosen local env is never a deployment default. `pytest tests/test_resume_chain.py tests/test_matching_vacancies.py tests/test_processing_artifacts.py` verifies correction/reuse, text invalidation, empty catalog and legacy behavior with controlled model responses; it is not a model-quality benchmark.
