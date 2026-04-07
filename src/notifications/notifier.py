"""Notification system — send alerts for pipeline events.

Supports console logging (always), with stubs for email and
desktop notifications.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    """A notification event."""
    title: str
    body: str
    level: str = "info"  # info, warning, error, success
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class ConsoleNotifier:
    """Send notifications to the console/log."""

    def send(self, notification: Notification):
        """Log notification to console."""
        level_map = {
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "success": logging.INFO,
        }
        lvl = level_map.get(notification.level, logging.INFO)
        icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "success": "✅"}.get(
            notification.level, "📋"
        )
        logger.log(lvl, f"{icon} {notification.title}: {notification.body}")


class EmailNotifier:
    """Send notifications via email using SMTP."""

    def __init__(
        self,
        smtp_host: str = "",
        smtp_port: int = 587,
        email: str = "",
        password: str = "",
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.email = email
        self.password = password
        self.use_tls = use_tls

    def send(self, notification: Notification):
        """Send email notification via SMTP. Falls back to logging if not configured."""
        if not (self.smtp_host and self.email and self.password):
            logger.info(
                f"[EMAIL STUB] Would send to {self.email}: "
                f"{notification.title} — {notification.body}"
            )
            return

        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[ATS Optimizer] {notification.title}"
        msg["From"] = self.email
        msg["To"] = self.email

        body = f"{notification.title}\n\n{notification.body}\n\nTimestamp: {notification.timestamp}"
        msg.attach(MIMEText(body, "plain"))

        try:
            if self.use_tls:
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.email, self.password)
                    server.sendmail(self.email, self.email, msg.as_string())
            else:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                    server.login(self.email, self.password)
                    server.sendmail(self.email, self.email, msg.as_string())
            logger.info(f"Email sent: {notification.title}")
        except Exception as e:
            logger.error(f"Email send failed: {e}")


class NotificationManager:
    """Central notification manager — dispatches to all configured channels."""

    def __init__(self):
        self.channels: list = [ConsoleNotifier()]
        self._history: list[Notification] = []

    def add_channel(self, channel):
        """Add a notification channel."""
        self.channels.append(channel)

    def notify(self, title: str, body: str, level: str = "info"):
        """Send a notification to all channels.

        Args:
            title: Short title.
            body: Notification body.
            level: One of info, warning, error, success.
        """
        notif = Notification(title=title, body=body, level=level)
        self._history.append(notif)
        for channel in self.channels:
            try:
                channel.send(notif)
            except Exception as e:
                logger.error(f"Notification send error: {e}")

    def notify_pipeline_complete(self, result):
        """Send a summary notification after pipeline run.

        Args:
            result: PipelineResult from the orchestrator.
        """
        self.notify(
            title="Pipeline Complete",
            body=(
                f"Discovered: {result.jobs_discovered}, "
                f"New: {result.jobs_new}, "
                f"Resumes: {result.resumes_generated}, "
                f"Applied: {result.applications_submitted}, "
                f"Errors: {len(result.errors)}"
            ),
            level="success" if not result.errors else "warning",
        )

    def notify_captcha(self, url: str):
        """Alert user that a CAPTCHA needs manual solving."""
        self.notify(
            title="CAPTCHA Detected",
            body=f"Manual intervention required at: {url}",
            level="warning",
        )

    def notify_error(self, error: str):
        """Alert user of an error."""
        self.notify(title="Error", body=error, level="error")

    @property
    def history(self) -> list[Notification]:
        """Returns the notification history."""
        return list(self._history)
