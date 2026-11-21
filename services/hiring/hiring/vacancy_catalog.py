"""Public catalogue projection and resolution of the submitted vacancy revision."""

import uuid

import httpx

from hiring.errors import Problem
from hiring.schemas import PortalVacancyRef

REQUIREMENTS_PUBLIC_PATH = "/api/v1/public/vacancies"


def dependency_error():
    return Problem(503, "DEPENDENCY_UNAVAILABLE", "Каталог вакансий недоступен. Повторите позже.")


def fetch_catalog(origin, path, params=None, *, allow_missing=False):
    try:
        response = httpx.get(origin.rstrip("/") + path, params=params, timeout=3)
        if allow_missing and response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid catalogue response")
        return data
    except (httpx.HTTPError, ValueError) as exc:
        raise dependency_error() from exc


def publication_items(data):
    rows = data.get("items")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise dependency_error()
    return rows


def requirements_item(row):
    try:
        return {"ref": {"system": "requirements", "id": str(uuid.UUID(row["id"])), "revision": row["revision"]},
                "title": row["title"], "position_code": row["position_code"],
                "description": row["description"], "published_at": row["published_at"], "is_synthetic": False}
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise dependency_error() from exc


def legacy_publications(settings):
    if not settings.portal_legacy_url:
        return []
    data = fetch_catalog(settings.portal_legacy_url, "/api/v1/vacancies", {"contour": "training"})
    rows = []
    for row in publication_items(data):
        if (row.get("status") != "open" or row.get("approved_profile_is_training") is not True
                or not row.get("approved_profile_version")):
            continue
        try:
            rows.append({
                "ref": {"system": "legacy", "id": str(uuid.UUID(row["vacancy_id"])),
                        "revision": row["approved_profile_version"]},
                "title": row["title"], "position_code": row["position_code"], "employer": row["employer"],
                "is_synthetic": True,
            })
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise dependency_error() from exc
    return rows


def list_publications(settings):
    rows = publication_items(fetch_catalog(settings.requirements_url, REQUIREMENTS_PUBLIC_PATH))
    return [requirements_item(row) for row in rows] if rows else legacy_publications(settings)


def requirements_publication(settings, vacancy_id, organization_id=None):
    params = {"organization_id": str(organization_id)} if organization_id else None
    row = fetch_catalog(settings.requirements_url, f"{REQUIREMENTS_PUBLIC_PATH}/{vacancy_id}", params, allow_missing=True)
    return requirements_item(row) if row is not None else None


def read_publication(settings, vacancy_id):
    publication = requirements_publication(settings, vacancy_id)
    if publication is None:
        publication = next((row for row in legacy_publications(settings) if row["ref"]["id"] == str(vacancy_id)), None)
    if publication is None:
        raise Problem(404, "NOT_FOUND", "Вакансия больше не опубликована.")
    return publication


def resolve_published_vacancy(settings, organization_id, ref: PortalVacancyRef):
    publication = None
    if ref.system == "requirements":
        publication = requirements_publication(settings, ref.id, organization_id)
    elif str(organization_id) == settings.portal_training_organization_id:
        publication = next((row for row in legacy_publications(settings) if row["ref"]["id"] == str(ref.id)), None)
    if publication is None or publication["ref"]["id"] != str(ref.id) or publication["ref"]["revision"] != ref.revision:
        raise Problem(409, "VACANCY_NOT_AVAILABLE", "Вакансия недоступна или изменилась. Выберите её заново.", "vacancy_ref")
    return {**publication, "status": "published", "source": ref.system}
