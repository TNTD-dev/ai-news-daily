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
from app.agent.curator import CuratedItem, UserPreferences
from app.config import AppConfig
from app.database.models import Digest


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
        prefs: UserPreferences | None = None,
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
        base_subject = f"Your AI Daily Digest – {digest.digest_date:%Y-%m-%d}"
        subject = (
            self._generate_subject_with_llm(digest, curated_items, base_subject)
            if use_llm_subject
            else base_subject
        )

        text_intro = self._build_text_intro(digest, prefs, use_llm_intro, recommendations_explanation)
        text_body = self._build_text_body(digest, curated_items, text_intro)
        html_body = self._build_html_body(digest, curated_items, text_intro)

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
        prefs: UserPreferences | None,
        use_llm_intro: bool,
        recommendations_explanation: str | None,
    ) -> str:
        """Build the intro paragraph for the email (plain text)."""
        name = prefs.name if prefs and prefs.name else None
        greeting = f"Hi {name}," if name else "Hi there,"

        if use_llm_intro:
            try:
                intro = self._generate_intro_with_llm(digest, prefs, recommendations_explanation)
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
        prefs: UserPreferences | None,
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
    ) -> str:
        """Build the plain-text body of the email."""
        lines: list[str] = []
        lines.append(intro)
        lines.append("")

        # Digest main content (already markdown/text)
        lines.append(f"# {digest.title}")
        lines.append("")
        lines.append(digest.content)
        lines.append("")

        if curated_items:
            lines.append("Top recommendations:")
            lines.append("")
            for item in curated_items:
                source_label = item.source_type.capitalize()
                provider_part = f" ({item.provider})" if item.provider else ""
                lines.append(
                    f"- [{source_label}]{provider_part}: {item.title}\n  {item.url}"
                )

        lines.append("")
        lines.append("Best,")
        lines.append("AI News Daily")

        return "\n".join(lines)

    def _build_html_body(
        self,
        digest: Digest,
        curated_items: List[CuratedItem],
        intro: str,
    ) -> str:
        """Build a simple HTML body suitable for most email clients."""
        # Basic escaping for intro (very simple; digest content assumed safe markdown/html)
        intro_html = "<br>".join(intro.splitlines())

        # Build curated items HTML list
        curated_html = ""
        if curated_items:
            curated_html_lines: list[str] = []
            curated_html_lines.append("<h2>Top recommendations</h2>")
            curated_html_lines.append("<ul>")
            for item in curated_items:
                source_label = item.source_type.capitalize()
                provider_part = f" ({item.provider})" if item.provider else ""
                curated_html_lines.append(
                    f'<li><strong>{source_label}{provider_part}:</strong> '
                    f'<a href="{item.url}">{item.title}</a></li>'
                )
            curated_html_lines.append("</ul>")
            curated_html = "\n".join(curated_html_lines)

        html = f"""<html>
  <body>
    <p>{intro_html}</p>

    <h1>{digest.title}</h1>
    <div>
      {digest.content}
    </div>

    {curated_html}

    <p>Best,<br>AI News Daily</p>
  </body>
</html>"""

        return html


