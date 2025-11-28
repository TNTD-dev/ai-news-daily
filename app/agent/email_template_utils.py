"""
Utilities for building the premium digest email template.

Customize the branding by editing the constants below. These values are
referenced across the HTML builder so tweaking colors, fonts, or footer links
only requires changes in one place.
"""

from __future__ import annotations

import html
import re
import textwrap
from datetime import date
from typing import List

from app.agent.curator import CuratedItem


BRAND_NAME = "AI News Daily"
FONT_STACK = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"

COLORS = {
    "background": "#f5f7fb",
    "card_background": "#ffffff",
    "primary": "#1d4ed8",
    "accent": "#f97316",
    "text": "#1f2937",
    "muted_text": "#6b7280",
    "border": "#e5e7eb",
}

CTA_URL = "mailto:tntduc05@gmail.com"
CTA_TEXT = "Share feedback"


def format_digest_date(value: date) -> str:
    """Return human-friendly date string (e.g., Thursday, July 18, 2024)."""
    return value.strftime("%A, %B %d, %Y")


def sanitize_plain_text(content: str) -> str:
    """Strip HTML/Markdown artifacts to produce plain text."""
    if not content:
        return ""
    # Remove Markdown headers and extra whitespace
    content = re.sub(r"^#+\s*", "", content, flags=re.MULTILINE)
    # Remove simple HTML tags
    content = re.sub(r"<[^>]+>", "", content)
    # Collapse whitespace
    content = re.sub(r"\s+\n", "\n", content)
    return content.strip()


def summarize_content(content: str, max_chars: int = 320) -> str:
    """Return a concise summary capped at max_chars."""
    plain = sanitize_plain_text(content)
    if len(plain) <= max_chars:
        return plain
    truncated = textwrap.shorten(plain, width=max_chars, placeholder="…")
    return truncated


def build_curated_items_html(items: List[CuratedItem]) -> str:
    """Render curated items as HTML cards."""
    if not items:
        return (
            "<p style=\"margin:0;color:{muted};\">No additional highlights for today."
            "</p>".format(muted=COLORS["muted_text"])
        )

    rows: list[str] = []
    for item in items:
        provider = html.escape(item.provider or "Source")
        title = html.escape(item.title)
        summary = html.escape(sanitize_plain_text(item.summary or "")[:220])
        url = html.escape(item.url)
        source_label = html.escape(item.source_type.title())

        rows.append(
            f"""
            <tr>
                <td style="padding:16px 0;">
                    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-radius:12px;border:1px solid {COLORS['border']};background:{COLORS['card_background']};">
                        <tr>
                            <td style="padding:18px 22px;font-family:{FONT_STACK};">
                                <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;color:{COLORS['muted_text']};margin-bottom:6px;">
                                    {source_label} · {provider}
                                </div>
                                <div style="font-size:17px;font-weight:600;color:{COLORS['text']};margin-bottom:8px;">
                                    {title}
                                </div>
                                <div style="font-size:14px;line-height:1.55;color:{COLORS['muted_text']};margin-bottom:12px;">
                                    {summary or "Stay tuned for more details soon."}
                                </div>
                                <a href="{url}" style="font-size:14px;color:{COLORS['primary']};font-weight:600;text-decoration:none;">Read more →</a>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
            """
        )

    return "\n".join(rows)


def build_curated_items_text(items: List[CuratedItem]) -> str:
    """Render curated items as plain text."""
    if not items:
        return "No highlighted items for today."

    lines: list[str] = []
    for idx, item in enumerate(items, start=1):
        provider = item.provider or "Source"
        lines.append(f"{idx}. [{item.source_type.title()} · {provider}] {item.title}")
        if item.summary:
            lines.append(f"   {sanitize_plain_text(item.summary)}")
        lines.append(f"   {item.url}")
    return "\n".join(lines)


def build_recommendations_html(explanation: str | None) -> str:
    """Optional section describing why items were selected."""
    if not explanation:
        return ""

    safe_explanation = html.escape(explanation)
    return f"""
    <tr>
        <td style="padding:18px 22px;border-radius:10px;background:{COLORS['background']};font-family:{FONT_STACK};">
            <div style="font-size:13px;text-transform:uppercase;letter-spacing:0.08em;color:{COLORS['primary']};margin-bottom:6px;">
                Why these picks?
            </div>
            <div style="color:{COLORS['text']};font-size:15px;line-height:1.6;">
                {safe_explanation}
            </div>
        </td>
    </tr>
    """


def build_footer_html() -> str:
    """Footer with brand info and CTA."""
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
        <tr>
            <td style="padding:24px 32px;font-family:{FONT_STACK};color:{COLORS['muted_text']};font-size:13px;text-align:center;">
                <p style="margin:0 0 8px 0;">
                    You're receiving this digest because you subscribed to {BRAND_NAME}.
                </p>
                <p style="margin:0 0 16px 0;">
                    Want to tailor your interests or pause emails? Reply to this message and we'll take care of it.
                </p>
                <a href="{CTA_URL}" style="display:inline-block;padding:10px 18px;background:{COLORS['primary']};color:#ffffff;text-decoration:none;border-radius:999px;font-weight:600;">
                    {CTA_TEXT}
                </a>
                <p style="margin:18px 0 0 0;font-size:12px;color:{COLORS['muted_text']};">
                    © {date.today().year} {BRAND_NAME}. All rights reserved.
                </p>
            </td>
        </tr>
    </table>
    """

