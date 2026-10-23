const severity = { up: 0, degraded: 1, down: 2 };
export function summarize(services, samples, now, hours = 24, interval = 60) {
  const start = now - hours * 3600;
  return {
    generated_at: now,
    hours,
    interval,
    method:
      "Reachability is the fraction of observed checks that connected; coverage shows missing scheduled checks. Unknown time is not counted as uptime.",
    services: services.map((service) => {
      const records = samples
          .filter(
            (s) =>
              s.service_id === service.id && s.time >= start && s.time <= now,
          )
          .sort((a, b) => a.time - b.time),
        known = records.filter((s) => s.state in severity),
        expected = Math.ceil((hours * 3600) / interval),
        buckets = new Set(
          known.map((s) =>
            Math.min(expected - 1, Math.floor((s.time - start) / interval)),
          ),
        ),
        last = records.at(-1),
        state =
          last && now - last.time <= 2 * interval ? last.state : "unknown";
      const latencies = known
          .map((s) => s.latency)
          .filter((v) => v !== null)
          .sort((a, b) => a - b),
        incidents = [];
      let active = null,
        previous = null;
      for (const sample of records) {
        if (previous && sample.time - previous.time > 2 * interval && active) {
          active.ended = previous.time;
          active.resolution = "coverage gap";
          incidents.push(active);
          active = null;
        }
        if (["down", "degraded"].includes(sample.state)) {
          if (!active)
            active = {
              started: sample.time,
              ended: null,
              state: sample.state,
              resolution: "ongoing",
            };
          else if (sample.state === "down") active.state = "down";
        } else if (active) {
          active.ended = sample.time;
          active.resolution = "observed recovery";
          incidents.push(active);
          active = null;
        }
        previous = sample;
      }
      if (active) {
        if (state === "unknown") {
          active.ended = previous.time;
          active.resolution = "coverage gap";
        }
        incidents.push(active);
      }
      const series = Array.from({ length: 48 }, (_, i) => {
        const a = start + (i * hours * 3600) / 48,
          b = start + ((i + 1) * hours * 3600) / 48,
          matches = records.filter(
            (s) => s.time >= a && (s.time < b || (i === 47 && s.time === b)),
          ),
          worst = matches.sort(
            (a, b) => (severity[b.state] ?? -1) - (severity[a.state] ?? -1),
          )[0];
        return { time: a, state: worst?.state || "unknown" };
      });
      return {
        id: service.id,
        label: service.label,
        kind: service.kind,
        state,
        checked_at: last?.time ?? null,
        latency: last?.latency ?? null,
        reachability: known.length
          ? Math.round(
              (known.filter((s) => ["up", "degraded"].includes(s.state))
                .length /
                known.length) *
                10000,
            ) / 100
          : null,
        coverage: Math.round((buckets.size / expected) * 10000) / 100,
        samples: known.length,
        p95:
          latencies[Math.max(0, Math.ceil(latencies.length * 0.95) - 1)] ??
          null,
        incidents: incidents.reverse().slice(0, 20),
        series,
      };
    }),
  };
}
export function synthetic(now, scenario = "normal") {
  const services = [
      { id: "dns", label: "DNS Filter", kind: "http" },
      { id: "mesh", label: "Private Mesh", kind: "tcp" },
      { id: "media", label: "Media Box", kind: "http" },
      { id: "dev", label: "Dev Service", kind: "http" },
    ],
    samples = [];
  for (const [j, s] of services.entries())
    for (let i = 0; i <= 144; i++) {
      let state = j === 2 && i >= 70 && i < 76 ? "degraded" : "up";
      if (scenario === "incident" && j === 1 && i >= 131) state = "down";
      if (scenario === "recovery" && j === 1 && i >= 111 && i < 131)
        state = "down";
      if (scenario === "gap" && j === 0 && i >= 120) continue;
      samples.push({
        service_id: s.id,
        time: now - (144 - i) * 600,
        state,
        latency:
          state === "down"
            ? null
            : Math.round(
                (30 + j * 20 + Math.abs(Math.sin(i * 0.8)) * 50) * 100,
              ) / 100,
      });
    }
  return { services, samples };
}
