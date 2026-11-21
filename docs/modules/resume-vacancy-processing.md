# Resume processing and vacancy matching

The [contract](../contracts/resume-vacancy-stage-2.md) defines the new explicit commands. Existing saved-assessment reads remain unchanged.

`matching/intake.py` stores a checksum-addressed original, invokes existing parsing/redaction and creates Candidate/CandidateText without an Application. `assessment/facts.py` extracts typed source-grounded assertions and wraps the current evaluator. `assessment/artifacts.py` owns immutable technical results; the surrounding transaction publishes them. `matching/corrections.py` records HR corrections with expected-version checking. `assessment/service.py` retains arithmetic, three-valued qualification and evidence validation; the evidence client supplies reusable per-requirement/per-indicator semantic checks.

`matching/processing.py` coordinates unique profiles, preserves HR confirmations, writes compatible Assessments and saves dated runs. `live_catalog.py` reads legacy publications. `catalog_adapter.py` optionally reads Requirements with explicit checked bindings rather than silently treating its UUIDs as legacy profiles. The HTTP routes perform staff/contour authorization before processing or result disclosure.

Yandex is configured through existing LLMConfig defaults. Explicit openai_compat configuration can use LLM_API_KEY independently of YANDEX_API_KEY; it does not send the Yandex project header. Local Gemini credentials belong only in ignored deploy/local and are excluded from container context. No checked-in config selects Gemini.

One candidate can have an original, historical text versions, extracted facts and later HR correction. These are not merged into a global verified fact about a person. A model run never overwrites a confirmed HR assessment or creates an application. Search/qualification and the subsequent hiring decision remain separate.

Limitations: existing single-organization legacy access policy; no OCR, automatic identity merge, automatic Requirements profile translation or frontend integration. Model quality was not benchmarked by decision of the participant. The external catalog requires an authorized server credential and verified bindings; missing bindings remain visible. The target processing service may later be separated at these component interfaces without moving ownership of the source or кадрового решения.
