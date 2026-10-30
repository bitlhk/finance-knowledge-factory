"""Resource-bounded local probe stack; never operates on another Compose project.

Only loopback API/admin ports are published. Local throwaway credentials live in
ignored 0600 configuration, not command output. No production credentials used.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".m1-local/ragflow-service"
IMAGE = "infiniflow/ragflow@sha256:141670c7d25b4421f6378152e583a0fe7e5280ed750c42f7507759192d0dad82"
PROJECT = "kf-m1-ragflow"


def prepare():
    import yaml
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (STATE / "compose.json").exists():
        return
    password = secrets.token_hex(24)
    def store(name, data):
        fd = os.open(STATE / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(data)
    store("local-credentials.json", json.dumps({"password": password}))
    config = {
        "general": {"heartbeat_interval": "3s"},
        "api": {"host": "0.0.0.0", "http_port": 9380},
        "admin": {"host": "admin", "http_port": 9381},
        "mysql": {"name": "rag_flow", "user": "root", "password": password,
                  "host": "mysql", "port": 3306, "max_connections": 30},
        "minio": {"user": "probe", "password": password, "host": "minio:9000"},
        "es": {"hosts": "http://es01:9200", "username": "elastic", "password": password},
        "kvrocks": {"host": "kvrocks:6379", "password": password, "db": 1},
        "nats": {"host": "nats", "port": 4222},
        "otel": {"enable": False},
        "ingestor": {"mq_type": "nats", "max_concurrent_workers": 1, "page_concurrency": 1},
    }
    store("service.yaml", yaml.safe_dump(config))
    store("kvrocks.conf", f"bind 0.0.0.0\nport 6379\ndir /var/lib/kvrocks\nrequirepass {password}\n")
    services = {}
    def service(name, image, memory, **extra):
        services[name] = {"image": image, "mem_limit": memory, "cpus": 1.0,
                          "restart": "no", "security_opt": ["no-new-privileges:true"],
                          "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "2"}}, **extra}
    service("mysql", "mysql:8.0.40", "1200m",
            environment={"MYSQL_ROOT_PASSWORD": password, "MYSQL_DATABASE": "rag_flow"},
            command=["--innodb-buffer-pool-size=256M", "--max-connections=60"],
            volumes=["mysql:/var/lib/mysql"])
    service("minio", "pgsty/silo:RELEASE.2026-08-06T00-00-00Z", "512m",
            environment={"MINIO_ROOT_USER": "probe", "MINIO_ROOT_PASSWORD": password},
            command=["server", "/data"], volumes=["minio:/data"])
    service("kvrocks", "apache/kvrocks:2.16.0", "768m",
            user="0:0",
            command=["-c", "/etc/kvrocks/probe.conf"],
            volumes=[f"{STATE}/kvrocks.conf:/etc/kvrocks/probe.conf:ro", "kvrocks:/var/lib/kvrocks"])
    service("nats", "nats:2.14.2", "256m", command=["-js", "-sd", "/data"], volumes=["nats:/data"])
    service("es01", "elasticsearch:8.11.3", "2200m",
            environment={"discovery.type": "single-node", "xpack.security.enabled": "true",
                         "ELASTIC_PASSWORD": password, "ES_JAVA_OPTS": "-Xms1g -Xmx1g"},
            tmpfs=["/tmp:mode=1777,size=256m"], volumes=["es:/usr/share/elasticsearch/data"])
    for name, mode, memory in [("api", "api", "1800m"), ("admin", "admin", "768m"), ("ingestor", "ingestor", "3g")]:
        service(name, IMAGE, memory, entrypoint=["/ragflow/bin/ragflow_server"],
                command=["--"+mode, "--config", "/probe/service.yaml"] + (["--init-superuser"] if name=="admin" else []),
                # Upstream bootstrap admin is a default account, NOT this random password.
                # Loopback-only test stack; never expose it as a production deployment.
                environment={"DOC_ENGINE": "elasticsearch", "DB_TYPE": "mysql",
                             "GOMAXPROCS": "1", "GOMEMLIMIT": "600MiB" if name=="admin" else "1500MiB"},
                volumes=[f"{STATE}/service.yaml:/probe/service.yaml:ro"],
                ports=([f"127.0.0.1:{19380 if name=='api' else 19381}:{9380 if name=='api' else 9381}"] if name!="ingestor" else []))
    store("compose.json", json.dumps({"version": "2.4", "services": services,
                                     "volumes": {n: {} for n in ("mysql", "minio", "kvrocks", "nats", "es")}}, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["prepare", "pull", "dependencies", "migrate", "start", "status", "stop"])
    args = ap.parse_args()
    prepare()
    cmd = ["docker-compose", "-H", "unix:///var/run/docker.sock", "-p", PROJECT, "-f", str(STATE / "compose.json")]
    actions = {"pull": ["pull"], "dependencies": ["up", "-d", "mysql", "minio", "kvrocks", "nats", "es01"],
               "migrate": ["run", "--rm", "api", "--migrate", "--config", "/probe/service.yaml"],
               "start": ["up", "-d", "admin", "api", "ingestor"], "status": ["ps"], "stop": ["stop"]}
    if args.action != "prepare":
        raise SystemExit(subprocess.call(cmd + actions[args.action]))
    print("Prepared local-only stack; credentials not displayed.")


if __name__ == "__main__":
    main()
