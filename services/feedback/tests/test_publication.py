"""Detect suppressed-value disclosure, cross-group reads and publication replacement."""

from fastapi.testclient import TestClient

from feedback.api import create_app
from feedback.store import seed_demo
from tests.test_cycle import answer, call, open_cycle


def prepare_closed(client, rare=False):
    cycle = open_cycle(client)
    path = f"/cycles/{cycle['id']}"
    codes = call(client, "POST", path + "/access-codes", body={"group_key": "large", "count": 10})["codes"]
    for i, code in enumerate(codes):
        value = 1 if i < (9 if rare else 5) else 2
        call(
            client,
            "POST",
            path + "/responses",
            None,
            answer(code, value, "work" if i < 5 else "learning"),
            201,
        )
    code = call(client, "POST", path + "/access-codes", body={"group_key": "small", "count": 1})["codes"][0]
    call(client, "POST", path + "/responses", None, answer(code), 201)
    return call(client, "POST", path + "/close", body={"expected_revision": cycle["revision"]})


def publish(client, cycle):
    return call(
        client,
        "POST",
        f"/cycles/{cycle['id']}/publication",
        body={
            "expected_revision": cycle["revision"],
            "policy": {"k": 5},
            "policy_basis": "Training demonstration, not an anonymity guarantee",
        },
    )


def publication_path(client, database=None):
    cycle = prepare_closed(client)
    p = publish(client, cycle)
    assert publish(client, cycle)["id"] == p["id"]
    call(
        client,
        "POST",
        f"/cycles/{cycle['id']}/publication",
        body={"expected_revision": cycle["revision"], "policy": {"k": 2}, "policy_basis": "changed"},
        status=409,
    )
    large, small = p["groups"]
    assert large["response_count"] == 10 and large["topics"][0]["count"] == 5
    assert large["scales"][0]["categories"] == [
        {"value": 1, "status": "shown", "count": 5},
        {"value": 2, "status": "shown", "count": 5},
    ]
    assert small == {
        "key": "small",
        "label": "Small training group",
        "status": "suppressed",
        "reason": "GROUP_DISCLOSURE_POLICY",
    }
    path = f"/publications/{p['id']}"
    assert len(call(client, "GET", path, "manager")["groups"]) == 1
    assert call(client, "GET", path, "small-manager")["groups"] == [small]
    call(client, "GET", path, "hr", status=404)
    call(client, "GET", path, "outsider", status=404)
    call(client, "GET", path + "?group_key=small", "manager", status=422)
    rare = publish(client, prepare_closed(client, rare=True))
    categories = rare["groups"][0]["scales"][0]["categories"]
    assert categories == [{"value": 1, "status": "suppressed"}, {"value": 2, "status": "suppressed"}]
    return {
        "cycle_id": cycle["id"],
        "publication_id": p["id"],
        "publication": p,
        "rare_distribution": categories,
    }


def test_publication_path(tmp_path):
    database = tmp_path / "feedback.db"
    seed_demo(database)
    with TestClient(create_app(database)) as client:
        result = publication_path(client)
    with TestClient(create_app(database)) as client:
        assert call(client, "GET", f"/publications/{result['publication_id']}") == result["publication"]
