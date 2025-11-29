"""
Email delivery service for sending digest emails via SMTP or Resend.

This service handles:
- SMTP connection and authentication
- Email message formatting (multipart/alternative with text and HTML)
- Integration with EmailAgent for content generation
- Database tracking of email delivery status
- Comprehensive error handling for delivery failures
- Optional delivery via Resend HTTP API when RESEND_API_KEY is configured
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

import resend
from sqlalchemy.orm import Session

from app.agent.curator import CuratedItem
from app.agent.email import EmailAgent, EmailContent
from app.config import AppConfig
from app.database.models import Digest
from app.database.repositories import DigestRepository, UserProfileRepository
from app.profiles.user_profile import (
    UserProfileSettings,
    get_default_user_profile,
    load_user_profile,
)


class EmailService:
    """
    Service for sending digest emails via SMTP.
    
    Handles email composition, SMTP delivery, and database tracking
    of delivery status. All errors are logged and handled gracefully
    without raising exceptions to the caller.
    """

    def __init__(
        self,
        config: AppConfig,
        session: Session,
        email_agent: Optional[EmailAgent] = None,
    ) -> None:
        """
        Initialize email service with configuration and dependencies.
        
        Args:
            config: Application configuration containing email settings
            session: Database session for repository operations
            email_agent: Optional EmailAgent instance (created if not provided)
        """
        self.config = config
        self.email_config = config.email
        self.session = session
        self.email_agent = email_agent or EmailAgent(config)
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize repositories
        self.digest_repo = DigestRepository(session)
        self.user_profile_repo = UserProfileRepository(session)

    def send_digest_email(
        self,
        digest: Digest,
        curated_items: List[CuratedItem],
        user_email: str,
        user_profile: Optional[UserProfileSettings] = None,
        use_llm_subject: bool = False,
        use_llm_intro: bool = False,
        email_content_override: EmailContent | None = None,
    ) -> bool:
        """
        Send a digest email to the specified user.
        
        This method:
        1. Loads user profile if not provided
        2. Composes email content using EmailAgent
        3. Sends email via Resend (if configured) or SMTP
        4. Updates digest record to mark as sent on success
        
        Args:
            digest: Digest instance to send
            curated_items: List of curated items to include in email
            user_email: Recipient email address
            user_profile: Optional user profile (loaded from DB if not provided)
            use_llm_subject: Whether to use LLM for subject line enhancement
            use_llm_intro: Whether to use LLM for intro generation
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            # Load user profile if not provided
            if user_profile is None:
                user_profile = load_user_profile(self.session, user_email)
                self.logger.info(
                    f"Loaded user profile for email delivery: email={user_email}, "
                    f"digest_id={digest.id}"
                )
            
            # Check if user wants to receive digests
            if not user_profile.receive_daily_digest:
                self.logger.info(
                    f"User opted out of daily digests, skipping email: "
                    f"email={user_email}, digest_id={digest.id}"
                )
                return False
            
            # Compose email content using EmailAgent (or reuse provided override)
            if email_content_override is None:
                self.logger.info(
                    f"Composing email content: digest_id={digest.id}, "
                    f"digest_date={digest.digest_date}, recipient={user_email}"
                )
                email_content = self.email_agent.compose_digest_email(
                    digest=digest,
                    curated_items=curated_items,
                    prefs=user_profile,
                    use_llm_subject=use_llm_subject,
                    use_llm_intro=use_llm_intro,
                )
            else:
                email_content = email_content_override
            text_snippet = email_content.text_body.replace("\n", " ")[:160]
            self.logger.debug(
                "Email preview | subject=%s | snippet=%s",
                email_content.subject,
                text_snippet,
            )
            
            # Decide delivery channel: Resend API (if configured) or SMTP fallback
            if self.email_config.resend_api_key:
                self.logger.info(
                    "Sending email via Resend: from_email=%s, to_email=%s",
                    self.email_config.from_email,
                    user_email,
                )
                if not self._send_via_resend(
                    subject=email_content.subject,
                    text_body=email_content.text_body,
                    html_body=email_content.html_body,
                    from_email=self.email_config.from_email,
                    to_email=user_email,
                ):
                    return False
            else:
                # Legacy SMTP path (used when RESEND_API_KEY is not provided)
                message = self._create_email_message(
                    subject=email_content.subject,
                    text_body=email_content.text_body,
                    html_body=email_content.html_body,
                    from_email=self.email_config.from_email,
                    to_email=user_email,
                )

                self.logger.info(
                    "Sending email via SMTP: from_email=%s, to_email=%s, smtp_host=%s, smtp_port=%s",
                    self.email_config.from_email,
                    user_email,
                    self.email_config.host,
                    self.email_config.port,
                )

                if not self._send_via_smtp(message):
                    return False
            
            # Mark digest as sent in database
            updated_digest = self.digest_repo.mark_email_sent(digest.id)
            if updated_digest:
                self.session.commit()
                self.logger.info(
                    f"Successfully sent digest email and updated database: "
                    f"digest_id={digest.id}, recipient={user_email}"
                )
                return True
            else:
                self.logger.error(
                    f"Email sent but failed to update digest record: digest_id={digest.id}"
                )
                return False
                
        except Exception as e:
            self.logger.error(
                f"Unexpected error sending digest email: digest_id={digest.id}, "
                f"recipient={user_email}, error={e}",
                exc_info=True
            )
            return False

    def _create_email_message(
        self,
        subject: str,
        text_body: str,
        html_body: str,
        from_email: str,
        to_email: str,
    ) -> MIMEMultipart:
        """
        Create a multipart/alternative email message with text and HTML parts.
        
        Args:
            subject: Email subject line
            text_body: Plain text email body
            html_body: HTML email body
            from_email: Sender email address
            to_email: Recipient email address
            
        Returns:
            MIMEMultipart message ready for sending
        """
        # Create multipart message with alternative parts
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = from_email
        message["To"] = to_email
        
        # Add text part
        text_part = MIMEText(text_body, "plain", "utf-8")
        message.attach(text_part)
        
        # Add HTML part
        html_part = MIMEText(html_body, "html", "utf-8")
        message.attach(html_part)
        
        return message

    def _send_via_smtp(self, message: MIMEMultipart) -> bool:
        """
        Send email message via SMTP with proper TLS/SSL handling.
        
        Supports:
        - Port 587: TLS (STARTTLS)
        - Port 465: SSL
        
        Args:
            message: MIMEMultipart message to send
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            # Determine connection method based on port
            use_ssl = self.email_config.port == 465
            use_tls = self.email_config.port == 587
            
            if use_ssl:
                # SSL connection (port 465)
                self.logger.debug(
                    f"Connecting to SMTP server via SSL: host={self.email_config.host}, "
                    f"port={self.email_config.port}"
                )
                server = smtplib.SMTP_SSL(
                    self.email_config.host,
                    self.email_config.port,
                )
            else:
                # Regular connection (will use STARTTLS for port 587)
                self.logger.debug(
                    f"Connecting to SMTP server: host={self.email_config.host}, "
                    f"port={self.email_config.port}"
                )
                server = smtplib.SMTP(
                    self.email_config.host,
                    self.email_config.port,
                )
            
            # Enable TLS for port 587
            if use_tls:
                server.starttls()
                self.logger.debug("STARTTLS enabled")
            
            # Authenticate
            self.logger.debug("Authenticating with SMTP server")
            server.login(self.email_config.user, self.email_config.password)
            
            # Send email
            self.logger.debug(
                f"Sending email: from_email={message['From']}, to_email={message['To']}"
            )
            server.send_message(message)
            
            # Close connection
            server.quit()
            
            self.logger.info(
                f"Email sent successfully: from_email={message['From']}, "
                f"to_email={message['To']}"
            )
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            self.logger.error(
                f"SMTP authentication failed: host={self.email_config.host}, "
                f"port={self.email_config.port}, user={self.email_config.user}, error={e}",
                exc_info=True
            )
            return False
            
        except smtplib.SMTPException as e:
            self.logger.error(
                f"SMTP error occurred: host={self.email_config.host}, "
                f"port={self.email_config.port}, error={e}",
                exc_info=True
            )
            return False
            
        except Exception as e:
            self.logger.error(
                f"Unexpected error sending email via SMTP: host={self.email_config.host}, "
                f"port={self.email_config.port}, error={e}",
                exc_info=True
            )
            return False

    def _send_via_resend(
        self,
        subject: str,
        text_body: str,
        html_body: str,
        from_email: str,
        to_email: str,
    ) -> bool:
        """
        Send email using the Resend API.

        This method is used when RESEND_API_KEY is configured in EmailConfig.
        It mirrors the behavior of _send_via_smtp in terms of logging and
        error handling so that callers can treat both channels identically.
        """
        if not self.email_config.resend_api_key:
            self.logger.error(
                "Resend API key is not configured but _send_via_resend was called"
            )
            return False

        try:
            # Configure Resend client
            resend.api_key = self.email_config.resend_api_key

            params = {
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                # Resend supports both html and text; provide both for better clients
                "html": html_body,
                "text": text_body,
            }

            self.logger.debug(
                "Calling Resend API to send email: from_email=%s, to_email=%s",
                from_email,
                to_email,
            )

            response = resend.Emails.send(params)  # type: ignore[attr-defined]

            message_id = None
            # Resend may return dict-like or object; try to log an identifier if present
            if isinstance(response, dict):
                message_id = response.get("id")
            elif hasattr(response, "id"):
                message_id = getattr(response, "id")

            self.logger.info(
                "Email sent successfully via Resend: from_email=%s, to_email=%s, message_id=%s",
                from_email,
                to_email,
                message_id,
            )
            return True

        except Exception as e:
            self.logger.error(
                "Unexpected error sending email via Resend: from_email=%s, to_email=%s, error=%s",
                from_email,
                to_email,
                e,
                exc_info=True,
            )
            return False

