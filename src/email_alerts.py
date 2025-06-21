"""
Email alert system for cost monitoring using free SMTP.
Much simpler than AWS SES - no verification required!
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import structlog
from .config import get_settings

logger = structlog.get_logger(__name__)


async def send_cost_alert_email(subject: str, body: str, to_email: str = None):
    """
    Send cost alert email via SMTP (Gmail, Outlook, etc).
    FREE and no AWS verification required!
    
    Args:
        subject: Email subject
        body: Email body text
        to_email: Recipient email (optional, uses config default)
    """
    settings = get_settings()
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = settings.from_email
        msg['To'] = to_email or settings.cost_alert_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        # Connect to SMTP server
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()  # Enable TLS encryption
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
        
        logger.info(
            "📧 Cost alert email sent successfully",
            subject=subject,
            to_email=to_email or settings.cost_alert_email,
            smtp_host=settings.smtp_host
        )
        return True
        
    except Exception as e:
        logger.error(
            "❌ Failed to send cost alert email",
            error=str(e),
            subject=subject,
            to_email=to_email or settings.cost_alert_email,
            smtp_host=settings.smtp_host
        )
        return False 