# Lantern: Homelab Health

A small dashboard for explicit HTTP/TCP service checks, incident history and missing-data coverage. [Try the synthetic browser demo](https://hirsu-dev.github.io/homelab-health/).

The public demo contains fictional services and generated samples. It has no access to my actual home network or yours.

## Features

- Reachable, slow, down and unknown states, shown with both words and colors.
- History windows, latency P95, incident records and sample coverage.
- Clear distinction between observed recovery and an unobserved coverage gap.
- A loopback-only Python server with optional explicit service checks and SQLite retention.
- HTTP checks with timeouts, no redirects and no response-body storage; TCP checks test port reachability only.
- JSON report export, responsive controls and keyboard-accessible service inspection.

## Run locally

Python 3.12+ is required.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m lantern
```

Open `http://127.0.0.1:8143`. The default is synthetic mode: it performs no network checks and creates no live-history database.

To enable live checks, copy `services.example.json` to the ignored `services.json`, replace its examples with services you own or are authorized to check, and list each exact host in `allowed_hosts`. Then run:

```powershell
.\.venv\Scripts\python.exe -m lantern --config services.json
```

On macOS/Linux use `.venv/bin/python` instead of `.\.venv\Scripts\python.exe`.

Checks are limited to 20 configured services, four concurrent probes and a 3-second timeout per connection/request operation. The worker finishes a collection batch before waiting the configured 30–3600 second interval; slower batches can reduce sample coverage. There is no subnet scan or service discovery. URL credentials, query strings and fragments are rejected. Targets and exception details are omitted from the report; bodies are never stored.

Live results are stored in ignored `data/lantern.sqlite`. `--database PATH` selects another file. Retention defaults to 7 days and accepts 1–30 days; older samples in this app's database are removed after collection. There are no outbound notifications, credentials or external analytics. Keep this account-free server local. Remote access needs a separate authenticated access design; the app is not a public monitoring endpoint.

## Reading the report

Observed reachability is the percentage of known samples that connected; slow samples count as reachable. Coverage is the number of observed scheduled time buckets divided by expected buckets. Neither metric fills missing time with success. A last sample older than two intervals becomes unknown.

The 48 history bins show the worst observed state in each bin. No sample means unknown. Incident boundaries are sample times, not precise outage times. A long sampling gap ends an incident as a coverage gap, not a recovery. P95 uses recorded connection latencies. Windows and exports contain up to 20 recent incidents per service; raw sample retention remains in SQLite.

HTTP reachability requires a 2xx status; an HTTP login redirect is shown as down. TCP reachability only confirms an accepted connection, not an application's internal health. There is no Pi-hole- or Tailscale-specific API integration in this first release.

## Development

```powershell
npm ci
npm run check
python -m unittest discover -s tests -p "test_*.py" -v
```

Node.js 22+ is used for frontend checks. To serve just the browser demo, run `python -m http.server 8144 --bind 127.0.0.1 --directory lantern/web` and open `http://127.0.0.1:8144/?demo=1`.

The checks cover missing coverage, absent samples, incident gaps, configured-host validation, redacted failures, collection lifecycle and the dashboard's actual scenario/inspection controls. Visual browser QA was unavailable during the release; review the page on your intended devices.

## Files

- `lantern/checker.py` validates explicit targets and performs probes.
- `lantern/core.py` builds the report without treating missing checks as uptime.
- `lantern/server.py` owns the background collector, SQLite retention and local API.
- `lantern/web` contains the browser UI and synthetic demo implementation.

GitHub Actions checks the app and deploys only `lantern/web` to Pages. No private configuration or database is published. Built by [hirsu](https://hirsu-dev.github.io/) from the Raspberry Pi home-lab idea.
