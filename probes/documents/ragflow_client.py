"""Supported HTTP API probe; only loopback, no production account or configuration."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import requests

STATE = Path(".m1-local/ragflow-service")
BASE = "http://127.0.0.1:19380/api/v1"


class Client:
    def __init__(self, email="knowledge-m1@example.invalid", password=None):
        self.session = requests.Session()
        self.password = password or json.loads((STATE / "local-credentials.json").read_text())["password"]
        r = self.session.post(BASE + "/auth/login", json={"email": email, "password": self.password}, timeout=30)
        body = r.json()
        if body.get("code") != 0:
            raise RuntimeError("LOGIN_FAILED:" + str(body.get("code")) + ":" + str(body.get("message")).replace(self.password, "[redacted]"))
        self.session.headers["Authorization"] = "Bearer " + r.headers["Authorization"]

    def call(self, method, path, **kwargs):
        r = self.session.request(method, BASE + path, timeout=120, **kwargs)
        body = r.json()
        if r.status_code >= 400 or body.get("code") != 0:
            raise RuntimeError(f"API_FAILED {method} {path} {r.status_code} {body.get('code')} " + str(body.get("message")).replace(self.password, "[redacted]"))
        return body.get("data")


def register(email):
    if email not in ("knowledge-m1@example.invalid", "knowledge-m1-other@example.invalid"):
        raise ValueError("LOCAL_PROBE_IDENTITY_ONLY")
    password = json.loads((STATE / "local-credentials.json").read_text())["password"]
    response = requests.post(BASE + "/users", json={"email": email, "password": password,
                             "nickname": email.split("@")[0]}, timeout=30)
    body = response.json()
    if response.status_code >= 400 or body.get("code") != 0:
        raise RuntimeError("REGISTRATION_FAILED:" + str(body.get("code")))
    print("Local probe account registered; no credentials displayed.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", choices=["knowledge-m1@example.invalid", "knowledge-m1-other@example.invalid"])
    args = ap.parse_args()
    if args.register:
        register(args.register)
        return
    client = Client()
    file = STATE / "http-setup.json"
    if file.exists():
        print("Setup already recorded; no duplicate writes.")
        return
    providers = client.call("GET", "/providers")
    if not any("OpenAI-API-Compatible" in str(p) for p in providers):
        client.call("PUT", "/providers", json={"provider_name": "OpenAI-API-Compatible"})
    net = json.loads(subprocess.check_output(["docker", "--host=unix:///var/run/docker.sock", "network", "inspect", "kf-m1-ragflow_default"]))[0]
    address = net["IPAM"]["Config"][0]["Gateway"]
    result = client.call("POST", "/providers/OpenAI-API-Compatible/instances", json={
        "instance_name": "m1_bge", "base_url": f"http://{address}:19382/v1", "api_key": client.password,
        "model_info": [{"model_name": "BAAI/bge-small-zh-v1.5", "model_type": ["embedding"], "max_tokens": 512}]})
    models = client.call("GET", "/models")
    # Models response may contain configuration; persist privately, print only names/keys.
    fd = os.open(file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(json.dumps({"models": models, "instance": result}, indent=2))
    print("Authenticated local API and embedding instance configured; private setup recorded.")


if __name__ == "__main__":
    main()
