"""Optional Requirements catalog reader with explicit, version-checked profile bindings."""
import json
import os
from pathlib import Path
import urllib.request
import urllib.error
from datetime import UTC, datetime
from sqlalchemy import select

from app.api.errors import ApiError
from app.assessment.artifacts import fingerprint
from app.db.models import RequirementProfile
from app.matching.schemas import VacancySnapshot
from app.matching.processing import profile_manifest
from app.matching.live_catalog import legacy_catalog


def current_catalog(session, contour):
    base = os.environ.get("HR_MATCHING_CATALOG_URL", "").rstrip("/")
    if not base:
        return legacy_catalog(session, contour), "legacy_catalog"
    token = os.environ.get("HR_MATCHING_CATALOG_TOKEN", "")
    mapping_path = os.environ.get("HR_MATCHING_PROFILE_MAP")
    try:
        bindings = json.loads(Path(mapping_path).read_text(encoding="utf-8")) if mapping_path else []
        if not isinstance(bindings, list):
            raise ValueError("bindings must be a list")
    except (OSError, ValueError):
        raise ApiError(503, "CATALOG_MAPPING_INVALID", "Реестр профилей недоступен или некорректен") from None

    def get(path):
        request = urllib.request.Request(base + path, headers={"Authorization": "Bearer " + token})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError):
            raise ApiError(503, "CATALOG_UNAVAILABLE", "Каталог недоступен или вернул некорректный ответ") from None

    result = []
    try:
        vacancies = get("/api/v1/catalog/vacancies?status=published")["items"]
        for vacancy in vacancies:
            if vacancy["status"] != "published":
                continue
            profile = get("/api/v1/profiles/" + vacancy["profile_id"])
            if profile["contour"] != contour:
                continue
            ref = {"system": "catalog", "id": profile["id"], "version": vacancy["profile_version"]}
            for binding in bindings:
                if (binding["catalog_profile_id"] == profile["id"]
                    and binding["catalog_version"] == vacancy["profile_version"] == profile["version"]
                    and binding["organization_id"] == vacancy["organization_id"] == profile["organization_id"]
                    and profile["position_code"] == vacancy["position_code"]
                    and binding["contour"] == contour and profile["is_current"]
                    and binding["catalog_content_hash"] == fingerprint(profile["content"])):
                    import uuid
                    local = session.get(RequirementProfile, uuid.UUID(binding["legacy_profile_id"]))
                    if local is not None and fingerprint(profile_manifest(local)) == binding["legacy_content_hash"]:
                        ref = {"system": "legacy-hr", "id": local.id, "version": local.version}
                        break
            result.append(VacancySnapshot(ref={"system": "catalog", "id": vacancy["id"]},
                revision=vacancy["revision"], title=vacancy["title"], description=vacancy["description"],
                position_code=vacancy["position_code"], status="published", contour=contour,
                observed_at=datetime.now(UTC), profile_ref=ref))
    except (KeyError, TypeError, ValueError):
        raise ApiError(503, "CATALOG_INVALID", "Некорректный снимок или реестр профилей") from None
    return result, "catalog_api"
