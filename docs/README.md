# ATS Optimizer — Documentation Hub

> **A fully-automated job application pipeline built for people who don't have time to job-hunt.**

---

## Who This Is For

| Persona | Pain Point |
|---|---|
| **Jobless candidate** | Applying to 50+ jobs/day manually is exhausting and demoralizing |
| **Toxic-job survivor** | No time or energy after work to search, tailor, apply |
| **Career switcher** | Needs resumes rewritten for every new domain |

The system eliminates **every manual step** between "I'm looking for a job" and "application submitted."

---

## How It Works (30-Second Summary)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Candidate   │────▸│  Job         │────▸│  Resume      │────▸│  Auto        │
│  Profile     │     │  Discovery   │     │  Tailoring   │     │  Apply       │
│  (5-10 pages)│     │  Engine      │     │  Engine      │     │  Engine      │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │                    │
       ▼                    ▼                    ▼                    ▼
  Your complete       Scrapes LinkedIn    Generates a unique   Fills forms,
  professional        Indeed, Glassdoor   ATS-optimized PDF    uploads resume,
  story in JSON       every few hours     for EACH job         submits — hands-free
```

---

## Documentation Index

| # | Document | What It Covers |
|---|---|---|
| 01 | [Requirements Analysis](01-requirements-analysis.md) | User personas, functional/non-functional requirements, constraints |
| 02 | [Candidate Profile System](02-candidate-profile-system.md) | The "master document" — schema, data capture, storage |
| 03 | [ATS Analysis Engine](03-ats-analysis-engine.md) | Scoring algorithm, keyword extraction, improvement suggestions |
| 04 | [Job Discovery Engine](04-job-discovery-engine.md) | Multi-portal scraping, deduplication, smart filtering |
| 05 | [Resume Generation Engine](05-resume-generation-engine.md) | LLM-powered tailoring, template system, PDF rendering |
| 06 | [Application Automation Engine](06-application-automation-engine.md) | Portal-specific drivers, form filling, CAPTCHA handling |
| 07 | [High-Level Architecture](07-high-level-architecture.md) | System diagram, service boundaries, data flow |
| 08 | [Low-Level Design](08-low-level-design.md) | Classes, DB schema, API contracts, config files |
| 09 | [Implementation Roadmap](09-implementation-roadmap.md) | Phased plan, milestones, tech stack decisions |

---

## Quick Start (Future — after implementation)

```bash
# 1. Fill your profile
python -m ats_optimizer profile init

# 2. Start the engine
python -m ats_optimizer run --portals linkedin,indeed --role "Backend Engineer"

# 3. Watch it work
open http://localhost:8501   # Streamlit dashboard
```
