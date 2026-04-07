"""FastAPI application entry point for ATS Optimizer."""

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from src.config import get_config
from src.database import get_engine, get_session_factory, init_db
from src.models import ApplicationLog, Job, Resume
from src.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ApplyRequest,
    ApplyResponse,
    ApplyResultItem,
    JobListResponse,
    JobResponse,
    JobUpdateRequest,
    KeywordInfo,
    PipelineStatusResponse,
    ProfileUpdateRequest,
    ResumeGenerateRequest,
    ResumeResponse,
)

# ── App Setup ────────────────────────────────────────────────

config = get_config()
engine = get_engine()
SessionFactory = get_session_factory(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup."""
    init_db(engine)
    yield


app = FastAPI(
    title=config.app.name,
    version=config.app.version,
    description="Automated job application pipeline with ATS optimization.",
    lifespan=lifespan,
)


def get_db() -> Session:
    """Dependency: get a DB session."""
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()


# ── Health Check ─────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {"status": "ok", "app": config.app.name, "version": config.app.version}


# ── Job Endpoints ────────────────────────────────────────────

@app.get("/jobs", response_model=JobListResponse)
def list_jobs(
    status: str | None = None,
    source: str | None = None,
    min_score: float | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List discovered jobs with optional filters."""
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
    if source:
        query = query.filter(Job.source == source)
    if min_score is not None:
        query = query.filter(Job.match_score >= min_score)

    total = query.count()
    jobs = query.order_by(Job.discovered_at.desc()).offset(offset).limit(limit).all()
    return JobListResponse(total=total, jobs=[JobResponse.model_validate(j) for j in jobs])


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    """Get a specific job by ID."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@app.patch("/jobs/{job_id}", response_model=JobResponse)
def update_job(job_id: int, update: JobUpdateRequest, db: Session = Depends(get_db)):
    """Update a job's status or notes."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if update.status:
        job.status = update.status
    if update.notes is not None:
        job.notes = update.notes
    db.commit()
    db.refresh(job)
    return JobResponse.model_validate(job)


# ── Analysis Endpoints ───────────────────────────────────────

@app.post("/analyze/score", response_model=AnalyzeResponse)
def analyze_score(request: AnalyzeRequest):
    """Score a resume against a job description using the ATS Analysis Engine."""
    from src.analyzer.scorer import ATSScorer
    from src.analyzer.suggestions import generate_suggestions

    scorer = ATSScorer()
    result = scorer.score(request.resume_text, request.job_description)
    suggestions = generate_suggestions(result)

    return AnalyzeResponse(
        overall_score=result.overall_score,
        breakdown={
            "keyword_match": result.breakdown.keyword_match,
            "section_completeness": result.breakdown.section_completeness,
            "keyword_density": result.breakdown.keyword_density,
            "experience_relevance": result.breakdown.experience_relevance,
            "formatting": result.breakdown.formatting,
        },
        missing_keywords=[
            KeywordInfo(
                keyword=kw["keyword"],
                category=kw.get("category", "general"),
                importance=kw.get("importance", "medium"),
            )
            for kw in result.missing_keywords
        ],
        suggestions=suggestions,
        formatting_issues=result.formatting_issues,
    )


# ── Profile Endpoints ────────────────────────────────────────

@app.get("/profile")
def get_profile():
    """Return the current candidate profile."""
    from src.profile.manager import ProfileManager

    pm = ProfileManager()
    if not pm.exists():
        raise HTTPException(status_code=404, detail="Profile not found. Create data/profiles/candidate_profile.yaml")
    profile = pm.load()
    return {
        "full_name": profile.full_name,
        "email": profile.email,
        "phone": profile.phone,
        "location": profile.location,
        "total_experience_years": profile.total_years_experience(),
        "skills": profile.get_all_skill_names(),
        "summaries_count": len(profile.summaries),
        "experience_count": len(profile.experience),
        "education_count": len(profile.education),
        "certifications_count": len(profile.certifications),
        "projects_count": len(profile.projects),
        "qa_bank_entries": len(profile.qa_bank),
    }


@app.patch("/profile")
def update_profile(update: ProfileUpdateRequest):
    """Update a section of the candidate profile.

    Supported sections: skills, experience, education, certifications, projects, summaries, qa_bank.
    """
    from src.profile.manager import ProfileManager

    pm = ProfileManager()
    if not pm.exists():
        raise HTTPException(status_code=404, detail="Profile not found")

    profile = pm.load()
    allowed = {"skills", "experience", "education", "certifications", "projects", "summaries", "qa_bank"}
    if update.section not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown section '{update.section}'. Allowed: {sorted(allowed)}")

    profile.data[update.section] = update.data
    pm.save(profile)
    return {"updated": update.section}


# ── Resume Endpoints ─────────────────────────────────────────

@app.get("/resumes", response_model=list[ResumeResponse])
def list_resumes(job_id: int | None = None, db: Session = Depends(get_db)):
    """List generated resumes, optionally filtered by job."""
    query = db.query(Resume)
    if job_id is not None:
        query = query.filter(Resume.target_job_id == job_id)
    return [ResumeResponse.model_validate(r) for r in query.order_by(Resume.created_at.desc()).all()]


@app.get("/resumes/{resume_id}", response_model=ResumeResponse)
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    """Get a specific generated resume."""
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return ResumeResponse.model_validate(resume)


@app.post("/resumes/generate", response_model=ResumeResponse)
def generate_resume_for_job(req: ResumeGenerateRequest, db: Session = Depends(get_db)):
    """Generate a tailored resume for a specific job and save it to the DB."""
    from src.profile.manager import ProfileManager
    from src.generator.content_selector import ContentSelector
    from src.generator.renderer import generate_resume
    from src.analyzer.scorer import ATSScorer

    job = db.query(Job).filter(Job.id == req.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    pm = ProfileManager()
    if not pm.exists():
        raise HTTPException(status_code=400, detail="Candidate profile not found")

    profile = pm.load()
    jd_text = job.description_text or job.title
    selector = ContentSelector()
    content = selector.select(profile, jd_text)

    template = f"{req.template}.html"
    output_dir = Path("data/output/resumes")
    files = generate_resume(content, output_dir, job_id=str(job.id), template=template)

    # Score the generated resume — build plain text from selected content
    resume_plain = " ".join([
        content.summary or "",
        " ".join(content.skills),
        " ".join(b.get("text", "") for exp in content.experience for b in exp.get("bullets", [])),
    ])
    scorer = ATSScorer()
    score_result = scorer.score(resume_plain, jd_text)

    resume = Resume(
        name=f"{profile.full_name} — {job.title} @ {job.company}",
        target_job_id=job.id,
        file_path=str(files.get("html", "")),
        ats_score=float(score_result.overall_score),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return ResumeResponse.model_validate(resume)


# ── Application Log Endpoints ────────────────────────────────

@app.get("/applications")
def list_applications(
    job_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """List application log entries."""
    query = db.query(ApplicationLog)
    if job_id is not None:
        query = query.filter(ApplicationLog.job_id == job_id)
    if status:
        query = query.filter(ApplicationLog.status == status)
    logs = query.order_by(ApplicationLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "job_id": log.job_id,
            "portal": log.portal,
            "status": log.status,
            "applied_at": log.timestamp,
            "duration_seconds": log.duration_seconds,
            "error_message": log.error_message,
            "questions_answered": len(log.questions_answered or []),
        }
        for log in logs
    ]


# ── Pipeline Endpoints ───────────────────────────────────────

# In-memory pipeline state (single-process; sufficient for CLI usage)
_pipeline_state: dict = {
    "is_running": False,
    "current_phase": None,
    "jobs_processed": 0,
    "jobs_applied": 0,
    "jobs_failed": 0,
    "started_at": None,
}


@app.get("/pipeline/status", response_model=PipelineStatusResponse)
def pipeline_status():
    """Get current pipeline run status."""
    return PipelineStatusResponse(**_pipeline_state)


@app.post("/pipeline/run")
async def run_pipeline(background_tasks: BackgroundTasks):
    """Trigger a pipeline run in the background using current config/profile."""
    if _pipeline_state["is_running"]:
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    background_tasks.add_task(_execute_pipeline)
    return {"message": "Pipeline started", "started_at": datetime.utcnow().isoformat()}


async def _execute_pipeline():
    """Background task: run discovery + resume generation pipeline."""
    import asyncio
    import os
    from src.automation.drivers.indeed import IndeedDriver
    from src.automation.drivers.linkedin import LinkedInDriver
    from src.automation.drivers.base import SearchConfig
    from src.automation.orchestrator import Orchestrator
    from src.profile.manager import ProfileManager
    from src.notifications.notifier import NotificationManager

    _pipeline_state["is_running"] = True
    _pipeline_state["started_at"] = datetime.utcnow()
    _pipeline_state["current_phase"] = "loading_profile"
    _pipeline_state["jobs_processed"] = 0
    _pipeline_state["jobs_applied"] = 0
    _pipeline_state["jobs_failed"] = 0

    notifier = NotificationManager()
    try:
        pm = ProfileManager()
        if not pm.exists():
            raise ValueError("Candidate profile not found")

        profile = pm.load()
        cfg = get_config()

        _pipeline_state["current_phase"] = "discovering_jobs"

        headless = cfg.browser.headless
        li_email = os.environ.get("LINKEDIN_EMAIL", "")
        li_password = os.environ.get("LINKEDIN_PASSWORD", "")

        drivers = [IndeedDriver(headless=headless)]
        if li_email and li_password:
            from src.automation.drivers.linkedin import LinkedInDriver
            drivers.append(LinkedInDriver(email=li_email, password=li_password, headless=headless))

        # Use top profile skills as search keywords
        top_skills = profile.get_all_skill_names()[:5]
        search_cfg = SearchConfig(keywords=top_skills)

        orch = Orchestrator(
            drivers=drivers,
            profile=profile,
            min_score=cfg.scoring.auto_apply_threshold,
            salary_expectation=os.environ.get("SALARY_EXPECTATION", "Negotiable"),
            notice_period=os.environ.get("NOTICE_PERIOD", "Immediate / 30 days"),
            work_authorization=os.environ.get("WORK_AUTHORIZATION", "Yes, authorized to work"),
            remote_preference=os.environ.get("REMOTE_PREFERENCE", "Remote or Hybrid preferred"),
        )
        result = await orch.run(search_cfg)

        _pipeline_state["jobs_processed"] = result.jobs_scored
        _pipeline_state["jobs_applied"] = result.applications_submitted
        _pipeline_state["jobs_failed"] = result.applications_failed
        _pipeline_state["current_phase"] = "complete"

        notifier.notify_pipeline_complete(result)

    except Exception as e:
        _pipeline_state["current_phase"] = "error"
        notifier.notify_error(str(e))
    finally:
        _pipeline_state["is_running"] = False


# ── Config Endpoint ──────────────────────────────────────────

@app.get("/config")
def get_app_config():
    """Return current app configuration (no secrets)."""
    cfg = get_config()
    return {
        "app": cfg.app.model_dump(),
        "llm": {
            "provider": cfg.llm.provider,
            "model": cfg.llm.model,
            "base_url": cfg.llm.base_url,
            "api_key_set": bool(cfg.llm.api_key),
        },
        "browser": cfg.browser.model_dump(),
        "scoring": cfg.scoring.model_dump(),
        "notifications": {
            "enabled": cfg.notifications.enabled,
            "method": cfg.notifications.method,
            "telegram_configured": bool(cfg.notifications.telegram_bot_token),
        },
    }

