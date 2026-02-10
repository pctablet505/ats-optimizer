"""Tests for Phase 7: Notifications, CLI, and integration."""

import pytest
import asyncio
from unittest.mock import patch
from io import StringIO

from src.notifications.notifier import (
    Notification,
    ConsoleNotifier,
    EmailNotifier,
    NotificationManager,
)
from src.automation.orchestrator import PipelineResult


# ── Notification Tests ───────────────────────────────────────

class TestNotification:
    def test_notification_defaults(self):
        n = Notification(title="Test", body="Body")
        assert n.level == "info"
        assert n.timestamp  # auto-generated

    def test_notification_custom_level(self):
        n = Notification(title="Alert", body="Error occurred", level="error")
        assert n.level == "error"


class TestConsoleNotifier:
    def test_send_logs(self, caplog):
        import logging
        with caplog.at_level(logging.INFO):
            notifier = ConsoleNotifier()
            notifier.send(Notification(title="Test", body="Hello"))
        assert "Test" in caplog.text

    def test_send_error(self, caplog):
        import logging
        with caplog.at_level(logging.ERROR):
            notifier = ConsoleNotifier()
            notifier.send(Notification(title="Fail", body="Broke", level="error"))
        assert "Fail" in caplog.text


class TestEmailNotifier:
    def test_stub_logs(self, caplog):
        import logging
        with caplog.at_level(logging.INFO):
            notifier = EmailNotifier(email="test@test.com")
            notifier.send(Notification(title="Job Alert", body="New match"))
        assert "EMAIL STUB" in caplog.text


class TestNotificationManager:
    def test_notify_adds_to_history(self):
        mgr = NotificationManager()
        mgr.notify("Title", "Body")
        assert len(mgr.history) == 1
        assert mgr.history[0].title == "Title"

    def test_multiple_notifications(self):
        mgr = NotificationManager()
        mgr.notify("A", "a")
        mgr.notify("B", "b")
        mgr.notify("C", "c")
        assert len(mgr.history) == 3

    def test_pipeline_complete_notification(self):
        mgr = NotificationManager()
        result = PipelineResult(
            jobs_discovered=10,
            jobs_new=8,
            resumes_generated=5,
            applications_submitted=3,
        )
        mgr.notify_pipeline_complete(result)
        assert len(mgr.history) == 1
        assert "success" == mgr.history[0].level

    def test_pipeline_with_errors(self):
        mgr = NotificationManager()
        result = PipelineResult(errors=["some error"])
        mgr.notify_pipeline_complete(result)
        assert mgr.history[0].level == "warning"

    def test_captcha_notification(self):
        mgr = NotificationManager()
        mgr.notify_captcha("https://example.com/apply")
        assert mgr.history[0].level == "warning"
        assert "CAPTCHA" in mgr.history[0].title

    def test_error_notification(self):
        mgr = NotificationManager()
        mgr.notify_error("Connection failed")
        assert mgr.history[0].level == "error"

    def test_add_channel(self):
        mgr = NotificationManager()
        email = EmailNotifier(email="user@test.com")
        mgr.add_channel(email)
        assert len(mgr.channels) == 2  # Console + Email


# ── CLI Tests ────────────────────────────────────────────────

class TestCLI:
    def test_build_parser(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["search", "--keywords", "python", "backend"])
        assert args.command == "search"
        assert args.keywords == ["python", "backend"]
        assert args.min_score == 50.0

    def test_parser_profile_command(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["profile", "--show"])
        assert args.command == "profile"
        assert args.show is True

    def test_parser_analyze_command(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["analyze", "--resume", "r.txt", "--jd", "j.txt"])
        assert args.command == "analyze"
        assert args.resume == "r.txt"

    def test_parser_search_options(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "search",
            "--keywords", "python",
            "--location", "SF",
            "--remote",
            "--min-score", "70",
            "--auto-apply",
            "--portals", "linkedin", "indeed",
        ])
        assert args.remote is True
        assert args.min_score == 70.0
        assert args.auto_apply is True
        assert args.portals == ["linkedin", "indeed"]

    def test_main_no_command(self):
        from src.cli import main
        with patch("sys.argv", ["ats-optimizer"]):
            result = main()
        assert result == 1  # Should return 1 (no command)

    def test_profile_show(self, tmp_path):
        """Test profile show with a real profile file."""
        from src.cli import run_profile
        from src.profile.manager import ProfileManager, CandidateProfile

        profile_path = tmp_path / "profile.yaml"
        pm = ProfileManager(profile_path)
        pm.save(CandidateProfile({
            "personal_info": {"full_name": "Test User", "email": "t@t.com", "location": "NY"},
            "summaries": [],
            "skills": [],
            "experience": [],
            "education": [],
            "certifications": [],
            "projects": [],
            "qa_bank": [],
        }))

        class Args:
            show = True
            path = str(profile_path)

        result = run_profile(Args())
        assert result == 0


# ── End-to-End Integration Test ─────────────────────────────

class TestEndToEnd:
    def test_full_pipeline_integration(self):
        """Test the complete pipeline: discover → dedup → score → generate."""
        from src.profile.manager import CandidateProfile
        from src.automation.drivers.indeed import IndeedDriver
        from src.automation.orchestrator import Orchestrator
        from src.automation.drivers.base import SearchConfig

        profile = CandidateProfile({
            "personal_info": {"full_name": "Integration Test User", "email": "i@t.com"},
            "summaries": [{"target_role": "Dev", "text": "Experienced developer."}],
            "skills": [{"category": "L", "items": [
                {"name": "Python", "proficiency": "Expert", "years": 5},
                {"name": "Docker", "proficiency": "Advanced", "years": 3},
            ]}],
            "experience": [{"company": "Co", "title": "Dev", "start_date": "2020", "end_date": None, "bullets": [
                {"text": "Built systems with Python", "tags": ["Python"]},
            ]}],
            "education": [],
            "certifications": [],
            "projects": [],
            "qa_bank": [],
        })

        orch = Orchestrator(
            drivers=[IndeedDriver()],
            profile=profile,
            min_score=0.0,
            auto_apply=True,
        )
        config = SearchConfig(keywords=["python"])
        result = asyncio.get_event_loop().run_until_complete(orch.run(config))

        assert result.jobs_discovered > 0
        assert result.resumes_generated > 0
        assert result.applications_submitted > 0
        assert len(result.errors) == 0
