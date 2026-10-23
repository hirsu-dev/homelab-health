import math
from collections import defaultdict

STATES = {"up": 0, "degraded": 1, "down": 2}


def summarize(services, samples, now, hours=24, interval=60):
    start = now - hours * 3600
    rows = []
    for service in services:
        records = sorted(
            [
                s
                for s in samples
                if s["service_id"] == service["id"] and start <= s["time"] <= now
            ],
            key=lambda s: s["time"],
        )
        known = [s for s in records if s["state"] in STATES]
        reachable = sum(s["state"] in {"up", "degraded"} for s in known)
        expected = math.ceil(hours * 3600 / interval)
        buckets = {
            min(expected - 1, int((s["time"] - start) / interval)) for s in known
        }
        last = records[-1] if records else None
        state = (
            last["state"] if last and now - last["time"] <= 2 * interval else "unknown"
        )
        latency = sorted(s["latency"] for s in known if s["latency"] is not None)
        incidents = []
        active = None
        previous = None
        for sample in records:
            if previous and sample["time"] - previous["time"] > 2 * interval:
                if active:
                    active["ended"] = previous["time"]
                    active["resolution"] = "coverage gap"
                    incidents.append(active)
                    active = None
            if sample["state"] in {"down", "degraded"}:
                if not active:
                    active = {
                        "started": sample["time"],
                        "ended": None,
                        "state": sample["state"],
                        "resolution": "ongoing",
                    }
                elif sample["state"] == "down":
                    active["state"] = "down"
            elif active:
                active["ended"] = sample["time"]
                active["resolution"] = "observed recovery"
                incidents.append(active)
                active = None
            previous = sample
        if active:
            if state == "unknown":
                active["ended"] = previous["time"]
                active["resolution"] = "coverage gap"
            incidents.append(active)
        bins = []
        for i in range(48):
            a = start + i * hours * 3600 / 48
            b = start + (i + 1) * hours * 3600 / 48
            matches = [
                s for s in records if a <= s["time"] < b or (i == 47 and s["time"] == b)
            ]
            worst = (
                max(matches, key=lambda s: STATES.get(s["state"], -1))
                if matches
                else None
            )
            bins.append({"time": a, "state": worst["state"] if worst else "unknown"})
        rows.append(
            {
                "id": service["id"],
                "label": service["label"],
                "kind": service["kind"],
                "state": state,
                "checked_at": last["time"] if last else None,
                "latency": last["latency"] if last else None,
                "reachability": round(100 * reachable / len(known), 2)
                if known
                else None,
                "coverage": round(100 * len(buckets) / expected, 2),
                "samples": len(known),
                "p95": latency[max(0, math.ceil(len(latency) * 0.95) - 1)]
                if latency
                else None,
                "series": bins,
                "incidents": list(reversed(incidents))[:20],
            }
        )
    return {
        "generated_at": now,
        "hours": hours,
        "interval": interval,
        "services": rows,
        "method": "Reachability is the fraction of observed checks that connected; coverage shows missing scheduled checks. Unknown time is not counted as uptime.",
    }


def synthetic(now, scenario="normal"):
    services = [
        {"id": "dns", "label": "DNS Filter", "kind": "http"},
        {"id": "mesh", "label": "Private Mesh", "kind": "tcp"},
        {"id": "media", "label": "Media Box", "kind": "http"},
        {"id": "dev", "label": "Dev Service", "kind": "http"},
    ]
    samples = []
    for j, s in enumerate(services):
        for i in range(145):
            state = "degraded" if j == 2 and 70 <= i < 76 else "up"
            if scenario == "incident" and j == 1 and i >= 131:
                state = "down"
            if scenario == "recovery" and j == 1 and 111 <= i < 131:
                state = "down"
            if scenario == "gap" and j == 0 and i >= 120:
                continue
            samples.append(
                {
                    "service_id": s["id"],
                    "time": now - (144 - i) * 600,
                    "state": state,
                    "latency": None
                    if state == "down"
                    else round(30 + j * 20 + abs(math.sin(i * 0.8)) * 50, 2),
                }
            )
    return services, samples
