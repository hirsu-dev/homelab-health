import { summarize, synthetic } from "./model.js";
const $ = (s) => document.querySelector(s),
  esc = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
const stamp = (t) =>
  t
    ? new Date(t * 1000).toISOString().slice(0, 19).replace("T", " ") + " UTC"
    : "No check recorded";
const labels = {
  up: "Reachable",
  degraded: "Slow",
  down: "Down",
  unknown: "Unknown",
};
let mode = "synthetic",
  report = null,
  selected = null,
  timer = 0,
  sequence = 0;
function timeline(s) {
  return `<div class="timeline" role="img" aria-label="48 history bins for ${esc(s.label)}. Unknown bins indicate missing samples. Observed reachability ${s.reachability ?? "unavailable"} percent and coverage ${s.coverage} percent.">${s.series.map((b) => `<i data-state="${b.state}" title="${stamp(b.time)} / ${labels[b.state]}"></i>`).join("")}</div>`;
}
function details() {
  const s =
    report.services.find((s) => s.id === selected) || report.services[0];
  if (!s) {
    $("#details").innerHTML = '<p class="empty">No configured services.</p>';
    return;
  }
  selected = s.id;
  $("#details").innerHTML =
    `<div class="detail-grid"><div><p class="eyebrow">SERVICE DETAIL / ${esc(s.kind.toUpperCase())} CHECK</p><h2>${esc(s.label)}</h2><p>Latest result: <strong class="state" data-state="${s.state}">${labels[s.state]}</strong><br/>${stamp(s.checked_at)}</p><p>P95 connection latency: ${s.p95 === null ? "No samples" : s.p95.toFixed(1) + " ms"}<br/>Observed samples: ${s.samples}<br/>Coverage: ${s.coverage}%</p><p>${s.kind === "tcp" ? "TCP verifies a listening port only. It does not test application behavior." : "HTTP requires a 2xx response; redirects are not followed. Response bodies are not stored."}</p></div><div><h2>Recent incidents</h2><div class="incidents">${s.incidents.map((i) => `<article class="incident" data-state="${i.state}"><h3>${labels[i.state]} / ${esc(i.resolution)}</h3><p>${stamp(i.started)} → ${i.ended ? stamp(i.ended) : "No recovery observed"}</p></article>`).join("") || '<p class="empty">No slow/down incidents were observed in this window. Check coverage before treating that as a complete history.</p>'}</div></div></div>`;
  document
    .querySelectorAll("[data-inspect]")
    .forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.inspect === selected)),
    );
}
function render() {
  const counts = { up: 0, degraded: 0, down: 0, unknown: 0 };
  for (const s of report.services) counts[s.state]++;
  $("#summary").innerHTML = Object.entries(labels)
    .map(
      ([state, label]) =>
        `<div data-state="${state}"><b>${counts[state]}</b><span>${label.toUpperCase()}</span></div>`,
    )
    .join("");
  $("#updated").textContent = "Updated " + stamp(report.generated_at);
  $("#services").innerHTML = report.services
    .map(
      (s) =>
        `<article class="service"><div class="service-title"><h3>${esc(s.label)}</h3><span class="state" data-state="${s.state}">${labels[s.state]}</span></div>${timeline(s)}<p>${report.hours} HOUR WINDOW / EACH TILE SHOWS THE WORST OBSERVED STATE</p><div class="metrics"><div><strong>${s.reachability === null ? "—" : s.reachability + "%"}</strong><small>OBSERVED REACHABILITY</small></div><div><strong>${s.coverage}%</strong><small>SAMPLE COVERAGE</small></div></div><button class="inspect" data-inspect="${esc(s.id)}" aria-pressed="${s.id === selected}">Inspect checks & incidents →</button></article>`,
    )
    .join("");
  details();
}
async function load() {
  const token = ++sequence;
  $("#refresh").disabled = true;
  try {
    const hours = Number($("#window").value),
      scenario = $("#scenario").value;
    if (mode === "synthetic") {
      const now = Math.floor(Date.now() / 1000),
        { services, samples } = synthetic(now, scenario);
      report = { mode, ...summarize(services, samples, now, hours, 600) };
    } else {
      const res = await fetch(`/api/summary?hours=${hours}`, {
        signal: AbortSignal.timeout(8000),
      });
      if (!res.ok) throw Error("The local checker could not return a report.");
      const result = await res.json();
      if (token !== sequence) return;
      report = result;
    }
    if (token !== sequence) return;
    render();
    $("#message").textContent =
      mode === "synthetic"
        ? "Synthetic demonstration. These are fictional services and generated checks, not hirsu's actual network."
        : "Private local checks. Missing coverage and stale results remain unknown.";
  } catch (e) {
    if (token !== sequence) return;
    if (report) {
      const now = Date.now() / 1000;
      report = {
        ...report,
        services: report.services.map((s) => ({
          ...s,
          state:
            !s.checked_at || now - s.checked_at > report.interval * 2
              ? "unknown"
              : s.state,
        })),
      };
      render();
    }
    $("#message").textContent =
      e.message +
      " Last report may be stale. Refresh after checking the local server.";
  } finally {
    if (token === sequence) $("#refresh").disabled = false;
  }
}
function schedule() {
  clearInterval(timer);
  timer = $("#auto").checked
    ? setInterval(() => {
        if (!document.hidden) load();
      }, 30000)
    : 0;
}
$("#services").addEventListener("click", (e) => {
  const b = e.target.closest("[data-inspect]");
  if (b) {
    selected = b.dataset.inspect;
    details();
  }
});
$("#window").addEventListener("change", load);
$("#scenario").addEventListener("change", load);
$("#refresh").addEventListener("click", load);
$("#auto").addEventListener("change", schedule);
window.addEventListener("pagehide", () => clearInterval(timer));
$("#export").addEventListener("click", () => {
  if (!report) return;
  const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
    ),
    a = document.createElement("a");
  a.href = url;
  a.download = "lantern-health-report.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
async function init() {
  const local =
    ["127.0.0.1", "localhost"].includes(location.hostname) &&
    new URLSearchParams(location.search).get("demo") !== "1";
  if (local) {
    const res = await fetch("/api/config");
    if (!res.ok)
      throw Error(
        "Start python -m lantern, or use ?demo=1 for the browser demo.",
      );
    const config = await res.json();
    mode = config.mode;
  }
  $("#mode").textContent =
    mode === "live-local" ? "PRIVATE LOCAL CHECKS" : "SYNTHETIC PUBLIC DEMO";
  $("#scenario-label").hidden = mode === "live-local";
  $("#auto").checked = mode === "live-local";
  await load();
  schedule();
}
init().catch((e) => {
  $("#message").textContent = e.message;
  $("#mode").textContent = "CHECKER UNAVAILABLE";
});
