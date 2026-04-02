"""ATS Optimizer — Streamlit Dashboard.

Run with:
    streamlit run frontend/dashboard.py

Assumes the FastAPI backend is running at http://localhost:8000.
Start it with:
    uvicorn src.main:app --reload
"""

import requests
import streamlit as st

API_BASE = "http://localhost:8000"


def api_get(path: str, params: dict | None = None):
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to API. Start it with: uvicorn src.main:app --reload")
        return None
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_post(path: str, json: dict | None = None):
    try:
        r = requests.post(f"{API_BASE}{path}", json=json, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to API. Start it with: uvicorn src.main:app --reload")
        return None
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_patch(path: str, json: dict | None = None):
    try:
        r = requests.patch(f"{API_BASE}{path}", json=json, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


# ── Page Config ───────────────────────────────────────────────

st.set_page_config(
    page_title="ATS Optimizer",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────

with st.sidebar:
    st.title("📄 ATS Optimizer")
    st.caption("Automated Job Application Pipeline")
    st.divider()

    page = st.radio(
        "Navigate",
        ["🏠 Dashboard", "💼 Jobs", "📊 Analyze", "👤 Profile", "📋 Resumes", "⚙️ Config"],
    )
    st.divider()

    health = api_get("/health")
    if health:
        st.success(f"API: {health.get('app', 'ATS Optimizer')} v{health.get('version', '?')}")
    else:
        st.error("API offline")


# ── Dashboard Page ────────────────────────────────────────────

if page == "🏠 Dashboard":
    st.header("Pipeline Dashboard")

    status = api_get("/pipeline/status")
    if status:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Status", "🔄 Running" if status["is_running"] else "✅ Idle")
        col2.metric("Jobs Processed", status["jobs_processed"])
        col3.metric("Applications", status["jobs_applied"])
        col4.metric("Failures", status["jobs_failed"])

        if status.get("current_phase"):
            st.info(f"Phase: {status['current_phase']}")

    st.divider()

    col_a, col_b = st.columns([1, 2])
    with col_a:
        st.subheader("Run Pipeline")
        st.caption("Discovers jobs and generates tailored resumes using your profile.")
        if st.button("▶️ Start Pipeline", type="primary", use_container_width=True):
            result = api_post("/pipeline/run")
            if result:
                st.success(result.get("message", "Pipeline started"))
                st.rerun()

    with col_b:
        jobs_data = api_get("/jobs", params={"limit": 5})
        if jobs_data:
            st.subheader(f"Recent Jobs ({jobs_data['total']} total)")
            for job in jobs_data.get("jobs", []):
                with st.expander(f"{job['title']} @ {job['company']} — Score: {job['match_score']:.0f}"):
                    st.write(f"**Source:** {job['source'].title()}")
                    st.write(f"**Location:** {job.get('location', 'N/A')}")
                    st.write(f"**Status:** {job['status']}")
                    st.markdown(f"[Open Job]({job['url']})")


# ── Jobs Page ─────────────────────────────────────────────────

elif page == "💼 Jobs":
    st.header("Discovered Jobs")

    with st.expander("Filters", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            status_filter = st.selectbox("Status", ["", "NEW", "APPLIED", "SKIPPED", "FAILED"])
        with col2:
            source_filter = st.selectbox("Source", ["", "linkedin", "indeed"])
        with col3:
            min_score = st.slider("Min Match Score", 0, 100, 0)

    params: dict = {"limit": 100}
    if status_filter:
        params["status"] = status_filter
    if source_filter:
        params["source"] = source_filter
    if min_score:
        params["min_score"] = min_score

    jobs_data = api_get("/jobs", params=params)
    if jobs_data:
        jobs = jobs_data.get("jobs", [])
        st.caption(f"Showing {len(jobs)} of {jobs_data['total']} jobs")

        for job in jobs:
            score_color = "🟢" if job["match_score"] >= 70 else ("🟡" if job["match_score"] >= 50 else "🔴")
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"**{job['title']}** @ {job['company']}")
                    st.caption(f"{job.get('location', '')} · {job['source'].title()}")
                with col2:
                    st.metric("Match", f"{score_color} {job['match_score']:.0f}")
                with col3:
                    statuses = ["NEW", "APPLIED", "SKIPPED", "FAILED"]
                    idx = statuses.index(job["status"]) if job["status"] in statuses else 0
                    new_status = st.selectbox(
                        "Status",
                        statuses,
                        index=idx,
                        key=f"status_{job['id']}",
                        label_visibility="collapsed",
                    )
                    if new_status != job["status"]:
                        if api_patch(f"/jobs/{job['id']}", {"status": new_status}):
                            st.success("Updated")

                st.markdown(f"[View Job]({job['url']})")


# ── Analyze Page ──────────────────────────────────────────────

elif page == "📊 Analyze":
    st.header("ATS Resume Analyzer")
    st.caption("Paste resume text and a job description to get an ATS score and improvement suggestions.")

    col1, col2 = st.columns(2)
    with col1:
        resume_text = st.text_area("Resume Text", height=300, placeholder="Paste your resume text here...")
    with col2:
        jd_text = st.text_area("Job Description", height=300, placeholder="Paste the job description here...")

    if st.button("🔍 Analyze", type="primary"):
        if not resume_text or not jd_text:
            st.warning("Please provide both resume text and job description")
        else:
            with st.spinner("Analyzing..."):
                result = api_post("/analyze/score", {"resume_text": resume_text, "job_description": jd_text})

            if result:
                score = result["overall_score"]
                color = "🟢" if score >= 70 else ("🟡" if score >= 50 else "🔴")
                st.metric("ATS Score", f"{color} {score}/100")

                st.subheader("Score Breakdown")
                breakdown = result.get("breakdown", {})
                cols = st.columns(len(breakdown))
                for i, (key, val) in enumerate(breakdown.items()):
                    cols[i].metric(key.replace("_", " ").title(), f"{val}")

                missing = result.get("missing_keywords", [])
                if missing:
                    st.subheader(f"Missing Keywords ({len(missing)})")
                    st.write(", ".join(kw["keyword"] for kw in missing))

                suggestions = result.get("suggestions", [])
                if suggestions:
                    st.subheader("Improvement Suggestions")
                    for s in suggestions:
                        st.write(f"• {s}")


# ── Profile Page ──────────────────────────────────────────────

elif page == "👤 Profile":
    st.header("Candidate Profile")

    profile = api_get("/profile")
    if profile:
        col1, col2, col3 = st.columns(3)
        col1.metric("Name", profile.get("full_name", "N/A"))
        col2.metric("Experience", f"{profile.get('total_experience_years', 0)} yrs")
        col3.metric("Skills", len(profile.get("skills", [])))

        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            st.info(f"📧 {profile.get('email', 'N/A')}")
            st.info(f"📍 {profile.get('location', 'N/A')}")
            if profile.get("phone"):
                st.info(f"📱 {profile['phone']}")
        with col_b:
            st.write(f"**Experience roles:** {profile.get('experience_count', 0)}")
            st.write(f"**Education:** {profile.get('education_count', 0)}")
            st.write(f"**Certifications:** {profile.get('certifications_count', 0)}")
            st.write(f"**Projects:** {profile.get('projects_count', 0)}")
            st.write(f"**Q&A bank entries:** {profile.get('qa_bank_entries', 0)}")

        st.divider()
        st.subheader("Skills")
        skills = profile.get("skills", [])
        if skills:
            st.write(" · ".join(skills))
        else:
            st.info("No skills listed in profile")
    else:
        st.warning("Profile not found. Create `data/profiles/candidate_profile.yaml`")


# ── Resumes Page ──────────────────────────────────────────────

elif page == "📋 Resumes":
    st.header("Generated Resumes")

    resumes = api_get("/resumes")
    if resumes is not None:
        if not resumes:
            st.info("No resumes generated yet. Run the pipeline or use the Analyze page.")
        else:
            for r in resumes:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**{r.get('name', 'Resume')}**")
                        st.caption(f"Created: {str(r.get('created_at', ''))[:10]}")
                        if r.get("file_path"):
                            st.text(f"📁 {r['file_path']}")
                    with col2:
                        score = r.get("ats_score")
                        if score is not None:
                            color = "🟢" if score >= 70 else ("🟡" if score >= 50 else "🔴")
                            st.metric("ATS Score", f"{color} {score:.0f}")


# ── Config Page ───────────────────────────────────────────────

elif page == "⚙️ Config":
    st.header("Configuration")

    cfg = api_get("/config")
    if cfg:
        st.subheader("App")
        st.json(cfg.get("app", {}))

        st.subheader("LLM Provider")
        llm = cfg.get("llm", {})
        col1, col2 = st.columns(2)
        col1.metric("Provider", llm.get("provider", "stub"))
        col1.metric("Model", llm.get("model", ""))
        col2.metric("API Key Set", "✅ Yes" if llm.get("api_key_set") else "❌ No")

        st.subheader("Scoring Thresholds")
        scoring = cfg.get("scoring", {})
        col1, col2, col3 = st.columns(3)
        col1.metric("Auto-Apply Threshold", scoring.get("auto_apply_threshold", 70))
        col2.metric("Min ATS Score", scoring.get("min_ats_score", 70))
        col3.metric("Max Retry Generations", scoring.get("max_retry_generations", 2))

        st.subheader("Browser")
        st.json(cfg.get("browser", {}))

        st.caption("Edit `config/app.yaml` to change settings, then restart the server.")
