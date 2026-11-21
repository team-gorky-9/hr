"""Catalog transport contract, with a controlled HTTP response (not an external deployment test)."""
import io
import json
import uuid
import urllib.error
import pytest
from app.api.errors import ApiError
from app.matching.catalog_adapter import current_catalog


def test_unmapped_catalog_profile_remains_explicit(monkeypatch):
    vid,pid,org=map(str,(uuid.uuid4(),uuid.uuid4(),uuid.uuid4()))
    vacancy={"id":vid,"profile_id":pid,"profile_version":2,"organization_id":org,
             "revision":3,"title":"Учебная вакансия","description":"Разработка API",
             "position_code":"python-dev","status":"published"}
    profile={"id":pid,"version":2,"contour":"training","organization_id":org,"is_current":True,"content":{},"position_code":"python-dev"}
    def response(request, timeout):
        return io.BytesIO(json.dumps({"items":[vacancy]} if '/catalog/vacancies' in request.full_url else profile).encode())
    monkeypatch.setenv('HR_MATCHING_CATALOG_URL','https://catalog.invalid')
    monkeypatch.delenv('HR_MATCHING_PROFILE_MAP',raising=False)
    monkeypatch.setattr('urllib.request.urlopen',response)
    rows,mode=current_catalog(None,'training')
    assert mode=='catalog_api' and rows[0].ref.id==uuid.UUID(vid)
    assert rows[0].profile_ref.system=='catalog'
    assert rows[0].revision==3


def test_catalog_outage_is_not_empty_success(monkeypatch):
    monkeypatch.setenv('HR_MATCHING_CATALOG_URL','https://catalog.invalid')
    monkeypatch.delenv('HR_MATCHING_PROFILE_MAP',raising=False)
    def unavailable(*args,**kwargs):
        raise urllib.error.URLError('controlled outage')
    monkeypatch.setattr('urllib.request.urlopen',unavailable)
    with pytest.raises(ApiError) as exc:
        current_catalog(None,'training')
    assert exc.value.status_code==503
