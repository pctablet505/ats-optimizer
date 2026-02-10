"""FastAPI application entry point for ATS Optimizer."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from src.config import get_config
from src.database import get_engine, get_session_factory, init_db
from src.models import Job
from src.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    JobListResponse,
    JobResponse,
    JobUpdateRequest,
    KeywordInfo,
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

