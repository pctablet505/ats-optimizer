"""SQLAlchemy ORM models for ATS Optimizer."""

from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from src.database import Base


class Job(Base):
    """Discovered job listing."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String, nullable=True)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String, nullable=True)
    salary_range = Column(String, nullable=True)
    description_text = Column(Text, nullable=True)
    url = Column(String, unique=True, nullable=False)
    source = Column(String, nullable=False)  # linkedin | indeed | glassdoor
    match_score = Column(Float, default=0.0)
    status = Column(String, default="NEW")  # NEW | QUEUED | APPLIED | SKIPPED | FAILED | REVIEW_NEEDED
    discovered_at = Column(DateTime, default=lambda: datetime.now(UTC))
    applied_at = Column(DateTime, nullable=True)
    resume_path = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    resumes = relationship("Resume", back_populates="job")
    application_logs = relationship("ApplicationLog", back_populates="job")

    def __repr__(self):
        return f"<Job(id={self.id}, title='{self.title}', company='{self.company}', status='{self.status}')>"


class Resume(Base):
    """Generated resume for a specific job."""

    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=True)
    target_job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    content_snapshot = Column(JSON, nullable=True)  # Snapshot of selected content
    file_path = Column(String, nullable=True)
    ats_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    job = relationship("Job", back_populates="resumes")

    def __repr__(self):
        return f"<Resume(id={self.id}, name='{self.name}', ats_score={self.ats_score})>"


class ApplicationLog(Base):
    """Log entry for each application attempt."""

    __tablename__ = "application_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    portal = Column(String, nullable=False)
    status = Column(String, nullable=False)  # SUCCESS | FAILED | SKIPPED | MANUAL_NEEDED
    error_message = Column(Text, nullable=True)
    screenshot_path = Column(String, nullable=True)
    questions_answered = Column(JSON, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    job = relationship("Job", back_populates="application_logs")

    def __repr__(self):
        return f"<ApplicationLog(id={self.id}, job_id={self.job_id}, status='{self.status}')>"


class SearchRun(Base):
    """Record of a job search execution."""

    __tablename__ = "search_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portal = Column(String, nullable=False)
    search_query = Column(String, nullable=True)
    jobs_found = Column(Integer, default=0)
    jobs_new = Column(Integer, default=0)
    started_at = Column(DateTime, default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<SearchRun(id={self.id}, portal='{self.portal}', jobs_found={self.jobs_found})>"
