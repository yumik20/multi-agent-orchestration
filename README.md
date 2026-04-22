# Multi-Agent AI System — Code Samples

Selected code samples from a multi-agent orchestration platform I built to run real marketing operations for my enterprise AI startup. The system coordinates 6 specialized AI agents that handle daily intelligence gathering, content creation, and operational monitoring — this is production software doing real work, not a research prototype.

I also built the local dashboard app as a contribution to [OpenClaw](https://github.com/anthropics/openclaw) — it helps operators track agent performance, manage costs across LLM providers, and supervise multi-agent workflows without constantly watching logs.

**System overview:** 16,000+ lines of Python/JavaScript. Zero external dependencies. Manages agent scheduling, cross-platform data collection (LinkedIn, X, HN/Reddit, Substack), AI-powered qualification pipelines, real-time dashboard visualization, and a structured knowledge base with audit trails.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Dashboard (JS/CSS)                    │
│   Weekly calendar · Org chart · Cost tracking · Chat     │
├─────────────────────────────────────────────────────────┤
│                  Orchestration Server (Python)            │
│   Agent scheduling · Scan pipelines · Watchdogs          │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│ LinkedIn │    X     │ HN/Reddit│ Substack │   Events    │
│  Scanner │ Scanner  │ Scanner  │ Scanner  │   Scanner   │
├──────────┴──────────┴──────────┴──────────┴─────────────┤
│              Knowledge Base (Markdown + JSON)             │
│   Wiki · Evidence log · Qualification pipeline · Schemas │
└─────────────────────────────────────────────────────────┘
```

## Code Samples

### 1. `agent-orchestration/` — Multi-Agent Scheduling & Watchdog System

A scheduling engine that manages 6 AI agents with conflict-free time slots, stall detection, and graceful shutdown. Key features:

- **Schedule builder** — generates weekly calendars from agent configurations, detects time-slot overlaps, handles multi-day patterns
- **Stall watchdog** — monitors running agent jobs via checkpoint files; nudges agents to save partial work after 5 minutes of inactivity, then force-kills after 7 minutes
- **Scan orchestration** — subprocess wrapper with dual kill rules (absolute timeout + CSV-stall detection) for long-running data collection jobs

### 2. `knowledge-base/` — Structured Knowledge Management System

A markdown-first knowledge base with formal ingest, qualification, and promotion pipelines. Designed so both humans and LLMs can maintain it. Key features:

- **Layered architecture** — immutable sources → raw intake buffer → maintained wiki → durable outputs
- **Evidence tracking** — 34 evidence entries with provenance chains, confidence levels, and thesis mapping
- **Qualification pipeline** — every piece of incoming data is explicitly accepted, rejected, or deferred with audit trail
- **Schema-driven records** — formal templates for scan findings, qualification decisions, and wiki writebacks

### 3. `dashboard-visualization/` — Real-Time Operational Dashboard

A single-page dashboard that visualizes agent activity, costs, and schedules. No frameworks — vanilla JavaScript rendering engine. Key features:

- **Weekly schedule calendar** — time-positioned task blocks with overlap-aware lane assignment and a live "Now" line
- **Cost reconciliation** — tracks LLM token usage across providers (OpenAI, Anthropic, Google) with monthly ledgers
- **Execution timeline** — maps expected vs. actual agent runs, surfaces missed/failed tasks

### 4. `scan-pipeline/` — AI-Powered Data Collection & Qualification

Cross-platform intelligence gathering with AI-powered quality filtering. Key features:

- **Multi-source collector** — unified pipeline that normalizes data from LinkedIn, X, HN/Reddit, and Substack into a common schema
- **Gemini AI quality filter** — uses LLM to evaluate and filter collected data against research-relevant criteria
- **Chrome automation** — browser-based data collection with profile management and anti-throttling measures

## Technical Choices

- **Zero external dependencies** — the entire server runs on Python standard library only
- **Markdown-first knowledge base** — diff-friendly, deterministic, works for both human and LLM consumption
- **File-based state** — JSON state files instead of a database; simple, inspectable, portable
- **AppleScript integration** — macOS-native email and browser automation for enterprise tooling

## Context

I built this system to run real marketing operations for my enterprise AI startup — the agents scan LinkedIn, X, HN/Reddit, and Substack daily for market intelligence, generate content, and manage publishing workflows. The dashboard app was built as a contribution to OpenClaw, giving operators visibility into agent performance, LLM costs, and scheduling without manual log-reading.

The knowledge base grew out of a practical need: as the agents collected hundreds of signals per week, I needed a structured way to qualify, promote, and maintain durable knowledge that both humans and AI agents could rely on. The design reflects ideas from my published research ("The Organizational Intelligence Loop") on how enterprise AI systems can maintain auditable organizational knowledge.

The code demonstrates applied work in: agent orchestration, human-AI collaboration systems, NLP pipeline design, knowledge management, cost optimization, and operational monitoring.
