"""
Email agent for composing personalized digest emails.

This agent focuses on generating email-ready subject, text, and HTML bodies
from a Digest and curated content, optionally using Gemini for nicer intros
or subject lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.agent.base import BaseAgent
from app.agent.curator import CuratedItem
from app.agent.email_template_utils import (
    BRAND_NAME,
    COLORS,
    FONT_STACK,
    build_curated_items_html,
    build_curated_items_text,
    build_footer_html,
    build_recommendations_html,
    format_digest_date,
    sanitize_plain_text,
    summarize_content,
)
from app.config import AppConfig
from app.database.models import Digest
from app.profiles import UserProfileSettings


@dataclass
class EmailContent:
    """Structured email content returned by EmailAgent."""

    subject: str
    text_body: str
    html_body: str


class EmailAgent(BaseAgent):
    """
    Agent responsible for composing email content (subject, text, HTML)
    from a digest and curated items.
    """

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        self.email_config = config.email

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compose_digest_email(
        self,
        digest: Digest,
        curated_items: List[CuratedItem],
        prefs: UserProfileSettings | None = None,
        use_llm_subject: bool = False,
        use_llm_intro: bool = False,
        recommendations_explanation: str | None = None,
    ) -> EmailContent:
        """
        Compose subject, text, and HTML bodies for a daily digest email.

        Args:
            digest: Digest instance with content already generated.
            curated_items: List of curated items to highlight in the email.
            prefs: Optional user preferences for personalization.
            use_llm_subject: If True, use Gemini to enhance the subject line.
            use_llm_intro: If True, use Gemini to generate a natural intro.
            recommendations_explanation: Optional human-readable explanation
                of recommendations (e.g., from CuratorAgent.refine_recommendations_with_llm).
        """
        base_subject = f"Daily AI News Digest - {digest.digest_date:%m/%d/%Y}"
        subject = base_subject

        text_intro = self._build_text_intro(
            digest,
            prefs,
            use_llm_intro,
            recommendations_explanation,
        )
        text_body = self._build_text_body(
            digest=digest,
            curated_items=curated_items,
            intro=text_intro,
            recommendations_explanation=recommendations_explanation,
        )
        html_body = self._build_html_body(
            digest=digest,
            curated_items=curated_items,
            intro=text_intro,
            recommendations_explanation=recommendations_explanation,
        )

        return EmailContent(subject=subject, text_body=text_body, html_body=html_body)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_subject_with_llm(
        self,
        digest: Digest,
        curated_items: List[CuratedItem],
        fallback_subject: str,
    ) -> str:
        """Use Gemini to generate a more engaging subject line."""
        if not curated_items:
            return fallback_subject

        top_titles = ", ".join(ci.title for ci in curated_items[:3])
        prompt = f"""You are writing a short, engaging email subject line for a daily AI news digest.

The digest date is {digest.digest_date:%Y-%m-%d}.
Here are some of the top items included:
- {top_titles}

Write a concise subject line (max 80 characters) that feels professional but engaging.
Do not include emojis.
"""

        messages = [
            {
                "role": "system",
                "content": "You are an expert email copywriter for professional AI news digests.",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            subject = self._call_llm(messages=messages, temperature=0.7, max_tokens=40)
            subject = subject.strip().replace("\n", " ")
            return subject or fallback_subject
        except Exception as e:
            self._log_error("Failed to generate subject with LLM", exception=e)
            return fallback_subject

    def _build_text_intro(
        self,
        digest: Digest,
        prefs: UserProfileSettings | None,
        use_llm_intro: bool,
        recommendations_explanation: str | None,
    ) -> str:
        """Build the intro paragraph for the email (plain text)."""
        name = prefs.name if prefs and prefs.name else None
        greeting = ""

        if use_llm_intro:
            try:
                intro = self._generate_intro_with_llm(
                    digest,
                    prefs,
                    recommendations_explanation,
                )
                return f"{greeting}\n\n{intro}"
            except Exception as e:
                self._log_error("Failed to generate intro with LLM", exception=e)

        # Fallback deterministic intro
        line = (
            "Here's your daily digest of the most interesting AI updates, "
            "hand-picked across YouTube, OpenAI, and Anthropic."
        )
        if recommendations_explanation:
            return f"{greeting}\n\n{recommendations_explanation}\n\n{line}"
        return f"{greeting}\n\n{line}"

    def _generate_intro_with_llm(
        self,
        digest: Digest,
        prefs: UserProfileSettings | None,
        recommendations_explanation: str | None,
    ) -> str:
        """Ask Gemini to craft a short personalized intro."""
        name = prefs.name if prefs and prefs.name else "there"
        prefs_desc = ""
        if prefs:
            if prefs.topics:
                prefs_desc += f"- Preferred topics: {', '.join(prefs.topics)}\n"
            if prefs.providers:
                prefs_desc += f"- Preferred providers: {', '.join(prefs.providers)}\n"
            if prefs.formats:
                prefs_desc += f"- Preferred formats: {', '.join(prefs.formats)}\n"
            if prefs.expertise_level:
                prefs_desc += f"- Expertise level: {prefs.expertise_level}\n"

        prompt = f"""You are writing a short introductory paragraph for a daily AI news email.

User name: {name}
Digest date: {digest.digest_date:%Y-%m-%d}
User preferences:
{prefs_desc if prefs_desc else '- No explicit preferences were provided.'}

Recommendation explanation (if provided, summarize or echo it naturally):
{recommendations_explanation or '(none provided)'}

Write 2-3 sentences in a friendly, professional tone to introduce today's digest.
Do not use emojis.
"""

        messages = [
            {
                "role": "system",
                "content": "You are an expert email writer. You write short, friendly, professional intros.",
            },
            {"role": "user", "content": prompt},
        ]
        intro = self._call_llm(messages=messages, temperature=0.7, max_tokens=120)
        return intro.strip()

    def _build_text_body(
        self,
        digest: Digest,
        curated_items: List[CuratedItem],
        intro: str,
        recommendations_explanation: str | None,
    ) -> str:
        """Build the plain-text body of the email."""
        lines: list[str] = []
        lines.append(intro)
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"{digest.title} — {digest.digest_date:%Y-%m-%d}")
        lines.append("=" * 60)
        lines.append(sanitize_plain_text(digest.content))
        lines.append("")

        if recommendations_explanation:
            lines.append("Why these picks:")
            lines.append(sanitize_plain_text(recommendations_explanation))
            lines.append("")

        lines.append("Top recommendations:")
        lines.append(build_curated_items_text(curated_items))
        lines.append("")
        lines.append("More ways to get the most out of AI News Daily:")
        lines.append("- Reply to this email to adjust your preferences.")
        lines.append("- Share an article you think we should feature.")
        lines.append("")
        lines.append("Best,")
        lines.append(BRAND_NAME)

        return "\n".join(lines)

    def _build_html_body(
        self,
        digest: Digest,
        curated_items: List[CuratedItem],
        intro: str,
        recommendations_explanation: str | None,
    ) -> str:
        """Build a modern HTML body suitable for most email clients."""
        intro_html = "<br>".join(intro.splitlines())
        formatted_date = format_digest_date(digest.digest_date)
        hero_summary = summarize_content(digest.content, max_chars=360)
        curated_html = build_curated_items_html(curated_items)
        recommendations_html = build_recommendations_html(recommendations_explanation)

        html = f"""\
<html>
  <body style="margin:0;padding:0;background-color:{COLORS['background']};">
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:{COLORS['background']};padding:24px 0;">
      <tr>
        <td align="center">
          <table width="620" cellpadding="0" cellspacing="0" role="presentation" style="background:{COLORS['card_background']};border-radius:18px;box-shadow:0 12px 35px rgba(15,23,42,0.08);overflow:hidden;">
            <tr>
              <td style="background:{COLORS['primary']};padding:28px 32px;font-family:{FONT_STACK};color:#ffffff;">
                <div style="font-size:13px;letter-spacing:0.12em;text-transform:uppercase;opacity:0.8;">{BRAND_NAME}</div>
                <div style="font-size:26px;font-weight:600;margin-top:6px;">Daily Digest</div>
                <div style="font-size:14px;opacity:0.85;margin-top:4px;">{formatted_date}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:28px 32px;font-family:{FONT_STACK};color:{COLORS['text']};">
                <p style="font-size:15px;line-height:1.65;margin:0 0 20px 0;color:{COLORS['text']};">{intro_html}</p>
                <div style="background:{COLORS['background']};border:1px solid {COLORS['border']};border-radius:14px;padding:20px 24px;">
                  <h2 style="margin:0 0 8px 0;font-size:19px;color:{COLORS['text']};">{digest.title}</h2>
                  <p style="margin:0;font-size:15px;line-height:1.7;color:{COLORS['muted_text']};">{hero_summary}</p>
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 10px 32px;font-family:{FONT_STACK};">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
                  <tr>
                    <td>
                      <div style="font-size:13px;text-transform:uppercase;letter-spacing:0.08em;color:{COLORS['accent']};margin-bottom:6px;">Top recommendations</div>
                      <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
                        {curated_html}
                      </table>
                    </td>
                  </tr>
                  {recommendations_html}
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:10px 32px 32px 32px;">
                {build_footer_html()}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

        return html


