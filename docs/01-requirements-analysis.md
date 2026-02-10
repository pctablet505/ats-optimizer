# 01 — Requirements Analysis

## 1. Problem Statement

Job hunting in 2025+ is a numbers game: candidates must submit **50–200+ applications** to land a single interview. Each application demands:

1. Finding a relevant posting (5–15 min)
2. Reading the JD and deciding fit (5 min)
3. Tailoring resume keywords/summary (15–30 min)
4. Navigating the portal, filling forms, uploading (10–20 min)
5. Repeating for every single job

**Total per application: ~40–70 minutes.** A person stuck in a toxic job literally cannot afford this.

---

## 2. User Personas

### Persona A — "The Unemployed Grinder"
- **Situation**: Laid off, applying full-time.
- **Need**: Volume — apply to 50+ jobs/day without burnout.
- **Frustration**: Copy-pasting the same info into 10 different portals.

### Persona B — "The Trapped Employee"
- **Situation**: Overworked, toxic environment, no time after 7 PM.
- **Need**: Set-and-forget — configure once, let it run overnight.
- **Frustration**: By the time they apply, the job is already filled.

### Persona C — "The Career Switcher"
- **Situation**: Moving from e.g. Data Analyst → ML Engineer.
- **Need**: Smart tailoring — emphasize transferable skills differently per JD.
- **Frustration**: One resume doesn't fit all; can't manually rewrite for every role.

---

## 3. Functional Requirements

### FR-1: Candidate Profile System
| ID | Requirement | Priority |
|---|---|---|
| FR-1.1 | Accept a rich, multi-page professional profile (not just a resume) | P0 |
| FR-1.2 | Store structured data: skills, projects, roles, achievements, certifications, education, publications, tools, methodologies | P0 |
| FR-1.3 | Support incremental updates (add a new project, update a skill level) | P1 |
| FR-1.4 | Import from existing resume PDF/DOCX as a starting point | P1 |
| FR-1.5 | Support a "Q&A bank" for common application questions (visa status, years of exp, etc.) | P0 |

### FR-2: ATS Score Analysis
| ID | Requirement | Priority |
|---|---|---|
| FR-2.1 | Score a resume against a specific JD (0–100) | P0 |
| FR-2.2 | Identify missing keywords with category (hard skill, soft skill, certification) | P0 |
| FR-2.3 | Check formatting compliance (no tables, standard headers, parseable fonts) | P1 |
| FR-2.4 | Provide actionable improvement suggestions | P0 |

### FR-3: Job Discovery
| ID | Requirement | Priority |
|---|---|---|
| FR-3.1 | Scrape jobs from LinkedIn, Indeed, Glassdoor (minimum 3 portals) | P0 |
| FR-3.2 | Filter by: title, location, remote/hybrid, salary range, date posted | P0 |
| FR-3.3 | Deduplicate jobs posted on multiple portals | P1 |
| FR-3.4 | Auto-score each job against candidate profile | P0 |
| FR-3.5 | Blacklist companies or keywords (e.g., "staffing agency", specific companies) | P1 |
| FR-3.6 | Run on a configurable schedule (e.g., every 4 hours) | P1 |

### FR-4: Resume Generation
| ID | Requirement | Priority |
|---|---|---|
| FR-4.1 | Generate a unique, ATS-optimized PDF for **each** job application | P0 |
| FR-4.2 | Use LLM to rewrite professional summary targeting the specific JD | P0 |
| FR-4.3 | Re-order and cherry-pick skills, projects, achievements from the Candidate Profile | P0 |
| FR-4.4 | Maintain consistent, clean, ATS-friendly formatting | P0 |
| FR-4.5 | Support multiple base templates (1-page, 2-page, academic CV) | P2 |

### FR-5: Application Automation
| ID | Requirement | Priority |
|---|---|---|
| FR-5.1 | Automatically apply to jobs on LinkedIn (Easy Apply) | P0 |
| FR-5.2 | Automatically apply on Indeed (Easy Apply) | P0 |
| FR-5.3 | Handle Workday/Greenhouse/Lever portals (common enterprise ATS) | P1 |
| FR-5.4 | Fill text fields, dropdowns, radio buttons, upload resume | P0 |
| FR-5.5 | Answer screening questions from Q&A bank or LLM fallback | P0 |
| FR-5.6 | Pause on CAPTCHA / unknown question and alert the user | P0 |
| FR-5.7 | Log every application: success, failure, skipped (with reason) | P0 |
| FR-5.8 | Configurable daily application limit to avoid suspicion | P1 |

### FR-6: Dashboard & Monitoring
| ID | Requirement | Priority |
|---|---|---|
| FR-6.1 | View all discovered jobs with match scores | P0 |
| FR-6.2 | View application history and status | P0 |
| FR-6.3 | View/edit candidate profile | P1 |
| FR-6.4 | Start/stop automation runs | P0 |
| FR-6.5 | View generated resumes per job | P1 |

---

## 4. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Privacy** | All data stored locally. No cloud sync. Credentials encrypted at rest with OS keyring. |
| **Reliability** | Graceful degradation: if one portal fails, others continue. Retry with exponential backoff. |
| **Performance** | Resume generation < 15 seconds per job. Job scraping batch < 5 minutes for 100 jobs. |
| **Anti-Detection** | Human-like delays (2–8 sec between actions), randomized mouse movements, session reuse. |
| **Extensibility** | New portal support via a plugin/driver pattern — add a new class, no core changes. |
| **Observability** | Structured logging (JSON), error screenshots on failure, optional email/Telegram alerts. |

---

## 5. Constraints & Risks

| Constraint | Mitigation |
|---|---|
| **Account suspension risk** on LinkedIn/Indeed | Rate limiting, human-like behavior, daily caps, session cookies |
| **CAPTCHA blocking** | Pause-and-alert (no auto-solve in V1). Manual CAPTCHA solving via notification. |
| **Portal DOM changes** | Selector-based configs in YAML (not hardcoded). Easy to update without code changes. |
| **LLM API costs** (if using OpenAI/Gemini) | Local LLM option (Ollama + Llama 3), or batch requests, caching similar JDs |
| **Legal/TOS** | Educational/personal use. Respect robots.txt where possible. User assumes risk. |
| **Diverse portal UIs** | Driver-per-portal plugin system. Each portal is an independent module. |
