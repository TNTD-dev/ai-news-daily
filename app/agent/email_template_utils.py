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


def parse_digest_header(content: str) -> tuple[str, str, str]:
    """
    Parse digest content to extract title, intro, and remaining content.
    
    Returns:
        tuple: (title, intro, remaining_content)
        - title: Extracted from first ## header
        - intro: First paragraph after title (until next section)
        - remaining_content: Rest of content without title and intro
    """
    if not content:
        return "", "", ""
    
    lines = content.split('\n')
    title = ""
    intro_lines = []
    remaining_lines = []
    
    found_title = False
    found_intro_end = False
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Look for title in ## header
        if not found_title and (line.startswith('## ') or line.startswith('# ')):
            # Extract title (remove # and ##)
            title = re.sub(r'^#+\s*', '', line).strip()
            found_title = True
            i += 1
            # Skip empty lines after title
            while i < len(lines) and not lines[i].strip():
                i += 1
            continue
        
        # Collect intro paragraph (until next section or empty line + section)
        if found_title and not found_intro_end:
            if not line:
                # Empty line - check if next non-empty is a section header
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line.startswith('##') or next_line.startswith('###') or next_line.startswith('#'):
                        found_intro_end = True
                        # Don't include this empty line in remaining
                        i += 1
                        continue
                # Just an empty line in intro, keep it
                intro_lines.append('')
            elif line.startswith('##') or line.startswith('###') or line.startswith('#'):
                # Hit a section header, intro is done
                found_intro_end = True
                remaining_lines.append(lines[i])
            else:
                intro_lines.append(lines[i])
        else:
            # After intro, collect remaining content
            remaining_lines.append(lines[i])
        
        i += 1
    
    intro = '\n'.join(intro_lines).strip()
    remaining_content = '\n'.join(remaining_lines).strip()
    
    return title, intro, remaining_content


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
        # Use reason if available, otherwise fallback to summary
        reason_or_summary = item.reason if item.reason else (item.summary or "")
        display_text = html.escape(sanitize_plain_text(reason_or_summary)[:220])
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
                                    {display_text or "Stay tuned for more details soon."}
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
        # Use reason if available, otherwise fallback to summary
        reason_or_summary = item.reason if item.reason else (item.summary or "")
        if reason_or_summary:
            lines.append(f"   {sanitize_plain_text(reason_or_summary)}")
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


def markdown_to_html_email(markdown: str) -> str:
    """
    Convert markdown to HTML suitable for email clients.
    
    Supports: headers (h1-h3), links, bold, italic, lists, paragraphs.
    Uses inline styles for email client compatibility.
    Formats numbered items with circular badges and styled sections.
    """
    if not markdown:
        return ""
    
    lines = markdown.split('\n')
    html_parts: list[str] = []
    in_list = False
    list_type = None  # 'ul' or 'ol'
    current_item_number = 0
    in_numbered_item = False
    item_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        
        # Headers - professional dark color with accent for emphasis
        if line.startswith('### '):
            text = html.escape(line[4:].strip())
            html_parts.append(
                f'<h3 style="margin:36px 0 18px 0;font-size:20px;font-weight:700;color:{COLORS["text"]};line-height:1.4;letter-spacing:-0.01em;">{text}</h3>'
            )
            if in_list:
                html_parts.append(f'</{list_type}>')
                in_list = False
            if in_numbered_item:
                html_parts.append(_format_numbered_item(item_lines, current_item_number))
                in_numbered_item = False
                item_lines = []
        elif line.startswith('## '):
            text = html.escape(line[3:].strip())
            html_parts.append(
                f'<h2 style="margin:40px 0 22px 0;font-size:22px;font-weight:700;color:{COLORS["text"]};line-height:1.4;letter-spacing:-0.01em;">{text}</h2>'
            )
            if in_list:
                html_parts.append(f'</{list_type}>')
                in_list = False
            if in_numbered_item:
                html_parts.append(_format_numbered_item(item_lines, current_item_number))
                in_numbered_item = False
                item_lines = []
        elif line.startswith('# '):
            text = html.escape(line[2:].strip())
            html_parts.append(
                f'<h1 style="margin:32px 0 20px 0;font-size:24px;font-weight:700;color:{COLORS["text"]};line-height:1.4;letter-spacing:-0.01em;">{text}</h1>'
            )
            if in_list:
                html_parts.append(f'</{list_type}>')
                in_list = False
            if in_numbered_item:
                html_parts.append(_format_numbered_item(item_lines, current_item_number))
                in_numbered_item = False
                item_lines = []
        # Ordered list items - format with circular badges
        # Handle formats: "1. Title", "**1. Title**", "1.  **Title**" (new format)
        elif re.match(r'^(\*\*)?\d+\.\s+', line) or re.match(r'^\*\*\d+\.\s+', line) or re.match(r'^\d+\.\s+\*\*', line):
            # Close previous numbered item if exists
            if in_numbered_item:
                html_parts.append(_format_numbered_item(item_lines, current_item_number))
                item_lines = []
            
            # Match number and title - handle multiple formats:
            # 1. "**1. Title**" - both number and title bold
            # 2. "1. Title" - neither bold
            # 3. "1.  **Title**" - number not bold, title bold (new format)
            match = (
                re.match(r'^\*\*(\d+)\.\s+(.+?)\*\*$', line) or  # **1. Title**
                re.match(r'^(\d+)\.\s+\*\*(.+?)\*\*$', line) or  # 1. **Title** (new format)
                re.match(r'^(\d+)\.\s+(.+)$', line)              # 1. Title
            )
            if match:
                current_item_number = int(match.group(1))
                item_title = match.group(2).strip()
                # Remove markdown bold/italic from title (in case it's nested)
                item_title = re.sub(r'\*\*([^*]+)\*\*', r'\1', item_title)
                item_title = re.sub(r'__([^_]+)__', r'\1', item_title)
                in_numbered_item = True
                item_lines = [('title', item_title)]
            else:
                # Fallback to regular list
                if not in_list or list_type != 'ol':
                    if in_list:
                        html_parts.append(f'</{list_type}>')
                    html_parts.append(f'<ol style="margin:14px 0;padding-left:24px;color:{COLORS["muted_text"]};">')
                    in_list = True
                    list_type = 'ol'
                list_text = re.sub(r'^(\*\*)?\d+\.\s+', '', line)
                list_text = re.sub(r'\*\*', '', list_text)
                list_text = _process_inline_markdown(list_text)
                html_parts.append(f'<li style="margin:10px 0;font-size:15px;line-height:1.7;color:{COLORS["muted_text"]};">{list_text}</li>')
        # Check for Source: and Summary: patterns in numbered items
        # Handle both regular and indented bullet points (with leading spaces)
        elif in_numbered_item and (line.strip().startswith('*') or line.strip().startswith('-')) and '**Source:**' in line:
            # Extract source link - handle various formats
            source_match = re.search(r'\*\*Source:\*\*\s*\[([^\]]+)\]\(([^)]+)\)', line)
            if source_match:
                source_text = source_match.group(1)
                source_url = source_match.group(2)
                item_lines.append(('source', (source_text, source_url)))
        elif in_numbered_item and (line.strip().startswith('*') or line.strip().startswith('-')) and '**Summary:**' in line:
            # Extract summary text - may span multiple lines
            summary_match = re.search(r'\*\*Summary:\*\*\s*(.+)', line)
            if summary_match:
                summary_text = summary_match.group(1).strip()
                item_lines.append(('summary', summary_text))
        elif in_numbered_item and line.strip() and not line.strip().startswith('*') and not line.strip().startswith('-') and not re.match(r'^(\*\*)?\d+\.', line) and not line.strip().startswith('#'):
            # Regular paragraph in numbered item (continuation of summary or content)
            # Check if previous was summary to continue it
            if item_lines and item_lines[-1][0] == 'summary':
                # Append to existing summary
                prev_summary = item_lines[-1][1]
                item_lines[-1] = ('summary', prev_summary + ' ' + line.strip())
            else:
                item_lines.append(('paragraph', line))
        # Unordered list (only if not in a numbered item context)
        elif not in_numbered_item and (line.strip().startswith('- ') or line.strip().startswith('* ')):
            if not in_list or list_type != 'ul':
                if in_list:
                    html_parts.append(f'</{list_type}>')
                html_parts.append(f'<ul style="margin:14px 0;padding-left:24px;color:{COLORS["muted_text"]};">')
                in_list = True
                list_type = 'ul'
            list_text = line.strip()[2:].strip()  # Remove leading spaces and bullet marker
            list_text = _process_inline_markdown(list_text)
            html_parts.append(f'<li style="margin:10px 0;font-size:15px;line-height:1.7;color:{COLORS["muted_text"]};">{list_text}</li>')
        # Empty line
        elif not line.strip():
            if in_list:
                html_parts.append(f'</{list_type}>')
                in_list = False
            # Empty line might end a numbered item if we have content
            if in_numbered_item and item_lines and len(item_lines) > 1:
                # Check next line to see if it's a new item or header
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                    # If next line is a new numbered item or header, close current item
                    if (re.match(r'^(\*\*)?\d+\.\s+', next_line) or 
                        next_line.startswith('#') or 
                        next_line.startswith('##') or 
                        next_line.startswith('###')):
                        html_parts.append(_format_numbered_item(item_lines, current_item_number))
                        in_numbered_item = False
                        item_lines = []
            # Don't add empty line if we're collecting item content
            if not in_numbered_item:
                html_parts.append('<p style="margin:12px 0;"></p>')
        # Regular paragraph
        else:
            if in_numbered_item:
                # Continue collecting item content
                item_lines.append(('paragraph', line))
            else:
                if in_list:
                    html_parts.append(f'</{list_type}>')
                    in_list = False
                processed = _process_inline_markdown(line)
                html_parts.append(
                    f'<p style="margin:14px 0;font-size:15px;line-height:1.75;color:{COLORS["muted_text"]};">{processed}</p>'
                )
        
        i += 1
    
    # Close any open structures
    if in_list:
        html_parts.append(f'</{list_type}>')
    if in_numbered_item:
        html_parts.append(_format_numbered_item(item_lines, current_item_number))
    
    return '\n'.join(html_parts)


def _format_numbered_item(item_lines: list[tuple[str, str | tuple]], number: int) -> str:
    """Format a digest item with title, source link, and summary (no numbered badge)."""
    if not item_lines:
        return ""
    
    title = ""
    source = None
    summary_parts = []
    
    for item_type, content in item_lines:
        if item_type == 'title':
            title = html.escape(str(content))
        elif item_type == 'source':
            source = content  # (text, url) tuple
        elif item_type == 'summary':
            summary_parts.append(str(content))
        elif item_type == 'paragraph':
            summary_parts.append(str(content))
    
    # Build HTML - no box, clean layout, no numbered badge
    html_parts = []
    html_parts.append('<div style="margin:24px 0;">')
    
    # Title - bold, dark color for readability
    if title:
        html_parts.append(
            f'<div style="font-size:18px;font-weight:700;color:{COLORS["text"]};margin-bottom:10px;line-height:1.5;letter-spacing:-0.01em;">{title}</div>'
        )
    
    # Source link - subtle button style
    if source:
        source_text, source_url = source
        html_parts.append(
            f'<div style="margin-bottom:14px;">'
            f'<span style="font-size:13px;color:{COLORS["muted_text"]};text-transform:uppercase;letter-spacing:0.05em;font-weight:600;margin-right:8px;">Source:</span>'
            f'<a href="{html.escape(source_url)}" style="display:inline-block;padding:6px 14px;background:{COLORS["background"]};border:1px solid {COLORS["border"]};border-radius:6px;color:{COLORS["primary"]};text-decoration:none;font-size:14px;font-weight:600;line-height:1.4;">'
            f'🔗 {html.escape(source_text)}'
            f'</a>'
            f'</div>'
        )
    
    # Summary/Content - professional muted color for body text
    if summary_parts:
        summary_html = []
        for part in summary_parts:
            processed = _process_inline_markdown(str(part))
            # Split into sentences/paragraphs if needed
            if processed.strip():
                summary_html.append(
                    f'<p style="margin:0 0 14px 0;font-size:15px;line-height:1.75;color:{COLORS["muted_text"]};">{processed}</p>'
                )
        if summary_html:
            html_parts.append('<div style="margin-top:8px;">' + ''.join(summary_html) + '</div>')
    
    html_parts.append('</div>')
    
    return '\n'.join(html_parts)


def _process_inline_markdown(text: str) -> str:
    """Process inline markdown: links, bold, italic."""
    # Use placeholders to avoid conflicts during processing
    placeholders = {}
    placeholder_idx = 0
    
    def make_placeholder(content):
        nonlocal placeholder_idx
        key = f"__PLACEHOLDER_{placeholder_idx}__"
        placeholders[key] = content
        placeholder_idx += 1
        return key
    
    # Process links: [text](url) - do this first before escaping
    def replace_link(m):
        link_text = m.group(1)
        link_url = m.group(2)
        html_link = f'<a href="{html.escape(link_url)}" style="color:{COLORS["primary"]};text-decoration:none;font-weight:600;">{html.escape(link_text)}</a>'
        return make_placeholder(html_link)
    
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_link, text)
    
    # Process bold: **text** or __text__ - before escaping
    def replace_bold(m):
        bold_text = m.group(1) or m.group(2)
        html_bold = f'<strong style="font-weight:600;">{html.escape(bold_text)}</strong>'
        return make_placeholder(html_bold)
    
    text = re.sub(r'\*\*([^*]+)\*\*|__([^_]+)__', replace_bold, text)
    
    # Process italic: *text* or _text_ (but not ** or __) - before escaping
    def replace_italic(m):
        italic_text = m.group(1) or m.group(2)
        html_italic = f'<em style="font-style:italic;">{html.escape(italic_text)}</em>'
        return make_placeholder(html_italic)
    
    text = re.sub(r'(?<!\*)\*(?!\*)([^*]+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)([^_]+?)(?<!_)_(?!_)', replace_italic, text)
    
    # Now escape remaining text (but not our placeholders)
    # Split text into parts: placeholders and regular text
    parts = re.split(r'(__PLACEHOLDER_\d+__)', text)
    result_parts = []
    for part in parts:
        if part.startswith('__PLACEHOLDER_') and part.endswith('__'):
            result_parts.append(part)  # Keep placeholder as-is
        else:
            result_parts.append(html.escape(part))  # Escape regular text
    
    text = ''.join(result_parts)
    
    # Restore placeholders (they're already HTML-safe)
    for placeholder, html_content in placeholders.items():
        text = text.replace(placeholder, html_content)
    
    return text


def format_markdown_text(markdown: str) -> str:
    """
    Format markdown as readable plain text for email.
    
    Converts markdown to plain text while preserving structure.
    """
    if not markdown:
        return ""
    
    lines = markdown.split('\n')
    text_parts: list[str] = []
    
    for line in lines:
        stripped = line.strip()
        
        # Headers
        if stripped.startswith('### '):
            text = stripped[4:].strip()
            text_parts.append(f"\n{text}\n{'-' * len(text)}")
        elif stripped.startswith('## '):
            text = stripped[3:].strip()
            text_parts.append(f"\n{text}\n{'=' * len(text)}")
        elif stripped.startswith('# '):
            text = stripped[2:].strip()
            text_parts.append(f"\n{text}\n{'=' * len(text)}")
        # Lists - keep as is but clean up
        elif re.match(r'^\d+\.\s+', stripped) or stripped.startswith('- ') or stripped.startswith('* '):
            # Remove markdown links but keep text
            cleaned = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', stripped)
            # Remove bold/italic markers
            cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)
            cleaned = re.sub(r'__([^_]+)__', r'\1', cleaned)
            cleaned = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', cleaned)
            cleaned = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'\1', cleaned)
            text_parts.append(cleaned)
        # Empty line
        elif not stripped:
            text_parts.append('')
        # Regular paragraph
        else:
            # Remove markdown links but keep text and URL
            cleaned = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', stripped)
            # Remove bold/italic markers
            cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)
            cleaned = re.sub(r'__([^_]+)__', r'\1', cleaned)
            cleaned = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', cleaned)
            cleaned = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'\1', cleaned)
            text_parts.append(cleaned)
    
    return '\n'.join(text_parts).strip()


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

