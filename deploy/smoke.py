"""Exercise all nine real APIs through Nginx. No mock HTTP responses."""
import argparse
import json
import urllib.error
import urllib.request

SERVICES = ["legacy", "workforce", "requirements", "hiring", "students",
            "mobility", "social-support", "recognition", "feedback"]


def request(base, path, expected=200):
    try:
        with urllib.request.urlopen(base + path, timeout=15) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, body = exc.code, exc.read()
    if status != expected:
        raise RuntimeError(f"{path}: expected {expected}, received {status}")
    return body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    for service in SERVICES:
        spec = json.loads(request(base, f"/{service}/openapi.json"))
        assert spec["openapi"].startswith("3.") and spec["paths"], service
        assert any(s["url"] == f"/{service}" for s in spec.get("servers", [])), service
        page = request(base, f"/{service}/docs").decode()
        assert f"/{service}/openapi.json" in page, f"{service}: broken Swagger prefix"
        request(base, f"/{service}/this-route-does-not-exist", 404)
        print(f"{service}: OpenAPI, Swagger prefix, HTTP 404 OK")
    for path in ["/legacy/api/v1/health", "/workforce/ready", "/requirements/ready", "/hiring/ready"]:
        body = json.loads(request(base, path))
        assert body["status"] == "ok", path
        print(f"{path}: ready")
    for service, path in [("workforce", "/api/v1/session"),
                          ("students", "/api/v1/students/opportunities"),
                          ("mobility", "/api/v1/mobility/opportunities"),
                          ("social-support", "/api/v1/support/cases")]:
        request(base, f"/{service}{path}", 401)
    request(base, "/unknown/openapi.json", 404)
    print("Gateway routing and anonymous denial checks passed. This is not full domain acceptance.")


if __name__ == "__main__":
    main()
