from concurrent.futures import ThreadPoolExecutor
from .conftest import PREFIX, apply, headers, opportunity, post, server


def test_place_assignment_and_last_slot(database_url):
    with server(database_url) as client:
        opp = opportunity(client)
        first = apply(client, opp["id"])
        second = apply(client, opp["id"], "candidate2")
        assert client.get(PREFIX + f"/applications/{first['id']}", headers=headers("candidate2")).status_code == 404
        assert client.get(PREFIX + f"/applications/{first['id']}", headers=headers("hr_other")).status_code == 404
        assert client.get(PREFIX + "/opportunities", headers=headers("candidate")).json()["items"][0]["available_places"] == 1
        # Two real requests contend for the last slot. Exactly one may commit.
        def assign(row):
            return client.post(PREFIX + f"/applications/{row['id']}/assign", headers=headers(),
                               json={"expected_revision": 1, "confirmation_basis": "Учебная ручная сверка"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(assign, [first, second]))
        assert sorted(r.status_code for r in responses) == [200, 409]
        winner = next(r.json() for r in responses if r.status_code == 200)
        loser = first if first["id"] != winner["application_id"] else second
        assert next(r.json() for r in responses if r.status_code == 409)["error"]["code"] == "CAPACITY_UNAVAILABLE"
        replay = post(client, f"/applications/{winner['application_id']}/assign",
                      {"expected_revision": 1, "confirmation_basis": "Повтор"})
        assert replay["id"] == winner["id"]
        assert client.get(PREFIX + f"/applications/{loser['id']}", headers=headers()).json()["status"] == "submitted"
        assert client.get(PREFIX + "/opportunities", headers=headers("candidate")).json()["items"] == []
        # Another opportunity must respect the same mentor's overlapping load.
        extra = opportunity(client)
        another = apply(client, extra["id"])
        rejected = post(client, f"/applications/{another['id']}/assign",
                        {"expected_revision": 1, "confirmation_basis": "Проверка нагрузки"}, expected=409)
        assert rejected["error"]["code"] == "MENTOR_CAPACITY_UNAVAILABLE"
        print({"opportunity": opp["id"], "placement": winner["id"], "unassigned_application": loser["id"]})
    with server(database_url) as restarted:
        assert restarted.get(PREFIX + f"/placements/{winner['id']}", headers=headers()).json()["id"] == winner["id"]
