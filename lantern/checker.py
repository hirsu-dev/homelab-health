import json
import socket
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx

def load_config(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    interval = int(data.get("interval", 60))
    retention = int(data.get("retention_days", 7))
    if not 30 <= interval <= 3600 or not 1 <= retention <= 30:
        raise ValueError("Use a 30–3600 second interval and 1–30 day retention.")
    services = data.get("services", [])
    allowed = data.get("allowed_hosts", [])
    if not 1 <= len(services) <= 20 or not isinstance(allowed, list):
        raise ValueError("Configure 1–20 explicit services and an allowed_hosts list.")
    seen = set()
    for s in services:
        if not isinstance(s.get("id"), str) or not s["id"] or s["id"] in seen:
            raise ValueError("Service IDs must be unique nonempty strings.")
        seen.add(s["id"])
        if (
            not isinstance(s.get("label"), str)
            or not s["label"].strip()
            or len(s["label"]) > 100
        ):
            raise ValueError("Each service needs a short label.")
        warn = s.get("warn_ms", 500)
        if not isinstance(warn, (int, float)) or not 1 <= warn <= 10000:
            raise ValueError("warn_ms must be 1–10000.")
        if s.get("kind") == "http":
            url = urlsplit(s.get("url", ""))
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError(
                    "HTTP checks need an http(s) URL without credentials, query strings or fragments."
                )
            host = url.hostname
        elif s.get("kind") == "tcp":
            host = s.get("host")
            if not isinstance(s.get("port"), int) or not 1 <= s["port"] <= 65535:
                raise ValueError("TCP ports must be 1–65535.")
        else:
            raise ValueError("Supported check kinds are http and tcp.")
        if host not in allowed:
            raise ValueError(
                "Each service host must be listed explicitly in allowed_hosts."
            )
    return {"interval": interval, "retention_days": retention, "services": services}

def check_service(service, clock=time.monotonic):
    started = clock()
    try:
        if service["kind"] == "http":
            with httpx.Client(
                timeout=3, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream("GET", service["url"]) as response:
                    ok = 200 <= response.status_code < 300
        else:
            with socket.create_connection(
                (service["host"], service["port"]), timeout=3
            ):
                pass
            ok = True
        latency = round((clock() - started) * 1000, 2)
        return {
            "state": ("degraded" if latency > service.get("warn_ms", 500) else "up")
            if ok
            else "down",
            "latency": latency if ok else None,
        }
    except (httpx.HTTPError, OSError, ValueError):
        
        return {"state": "down", "latency": None}
