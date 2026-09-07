# FleetPulse
**Live demo:** http://app.63.176.86.97.nip.io/docs
> Real-time event monitoring with a grounded LLM copilot and a tool-using ops agent; demo domain: IoT device fleet.

![ci](https://github.com/beharhyseni/fleetpulse/actions/workflows/ci.yml/badge.svg)

FleetPulse is a small production-style event-monitoring platform, demonstrated on an IoT
device fleet: sources report telemetry to a FastAPI backend, a rules engine raises alerts,
and an LLM copilot plus a tool-using Ops Agent turn a noisy alert window into a grounded,
plain-language incident summary. It runs on Kubernetes, is provisioned with Terraform, and
deploys itself from GitHub Actions on every merge.

**Domain-agnostic by design.** The architecture (event ingestion, rules, alerts, grounded
summaries, an auditable agent) has no domain; devices are the demonstration dataset. The
same platform monitors transactions, servers, orders, or claims: swap the noun, keep the
architecture.

## Status / roadmap

- [x] **P0 — Scaffold**: FastAPI skeleton, ruff + mypy + pytest, pre-commit, CI
- [x] P1 — Core API: models, migrations, ingest, rules engine, seeder
- [x] P2 — Docker + local Kubernetes (k3s via Rancher Desktop)
- [x] P3 — Terraform + cloud k3s (live URL)
- [x] P4 — CI/CD: build, push, deploy on merge
- [x] P5 — Grounded LLM incident summariser (`/incidents/summary`, cites alert ids, mocked-seam tests)
- [ ] P6 — Observability polish (structured logs, metrics, rate limits)
- [ ] P7 — Ops Agent: tool-use loop, approval-gated writes, run tracing
- [ ] P8 — Agent evals + MCP server

## Quickstart

```bash
python3.12 -m venv .venv && source .venv/bin/activate
make install
cp .env.example .env   # add your ANTHROPIC_API_KEY (or skip: /incidents/summary returns 503)
make db-up
make migrate
make seed              # demo fleet with planted anomalies
make run               # http://localhost:8000/docs
make lint test
```

## Try the AI layer

The summariser reads the live alert window and writes an operator briefing that cites
device names and alert ids, and invents nothing (see `SYSTEM_PROMPT` in
`app/services/summarize.py`):

```bash
curl -s http://app.63.176.86.97.nip.io/incidents/summary | python3 -m json.tool
```

Returns 503 when no `ANTHROPIC_API_KEY` is configured; tests mock at the network seam,
so CI runs green with no key and no network.

## Architecture

Telemetry batches enter through `POST /telemetry`, are validated at the edge (pydantic),
ingested atomically (SQLAlchemy/Postgres), and evaluated by a rules engine that raises
deduplicated alerts, race-proofed by a partial unique index. Kubernetes runs it all
(probes, secrets, ingress); Terraform builds the node it runs on. On top of the alert
window, `GET /incidents/summary` assembles a token-frugal context (open alerts, per-device
aggregates, silent devices) and has claude-sonnet-4-6 write a grounded briefing: the
substrate the P7 agent will investigate with. Diagram lands at P6.

## Design decisions

Documented as they are made; summarised here at P6.
