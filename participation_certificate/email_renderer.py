"""Render branded certificate-delivery emails from config-driven content.

All editable copy (subjects, body fields, legal footer) lives in
``config_local.yaml`` under ``email:``. The renderer drops resolved fields into
a shared layout: ``participation_certificate/email_templates/layout.html`` and
``layout.txt``. There are no per-type template files.

Body fields accept a tiny markdown subset:

    **bold**          → <strong>bold</strong>           (text: bold)
    *italic*          → <em>italic</em>                 (text: italic)
    [label](url)      → <a href="url">label</a>         (text: label (url))

Empty fields render as empty strings; nothing is inserted in their slot. This
keeps the masterclass email (which has no post-CTA paragraph) from carrying
phantom whitespace.

Substitution is two-pass:

  1. Each body field + the footer is `string.Template`-substituted with runtime
     variables (first_name, talk_title, …).
  2. Resolved fields are markdown-converted (per-format) and inserted into the
     shared layout, alongside the same runtime variables (so the layout can use
     ${download_url} directly for the CTA href, etc.).

Any unresolved ``${var}`` raises `KeyError` — fail-fast on a typo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

from omegaconf import OmegaConf

from participation_certificate import conf
from participation_certificate.models.attendee import Attendee

TEMPLATES_DIR = Path(__file__).parent / "email_templates"

# Body fields that are inserted verbatim (no markdown handling, no paragraph
# wrapping). Everything else goes through the markdown converter.
_PLAIN_FIELDS = frozenset({"greeting", "cta_label", "signature", "sign_off"})

# Every key the shared layouts (layout.html / layout.txt) reference. The
# renderer merges email.body.default + email.body.<type> and asserts every
# required key is present after the merge — a clearer error than the cryptic
# `string.Template` KeyError that would otherwise surface.
_REQUIRED_FIELDS = frozenset(
    {
        "greeting",
        "intro",
        "download_intro",
        "cta_label",
        "post_cta",
        "closing",
        "signature",
        "sign_off",
    }
)


@dataclass(frozen=True)
class RenderedEmail:
    """Output of :func:`render_email` — subject + plain-text + HTML bodies."""

    subject: str
    text: str
    html: str


# ---------------------------------------------------------------------------
# Markdown subset
# ---------------------------------------------------------------------------

_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
# *italic* but not the inside of **bold** — the asterisk-adjacent lookarounds
# exclude both `**` and word characters touching the marker.
_MD_ITALIC = re.compile(r"(?<![*\w])\*([^*]+)\*(?![*\w])")

# Paragraph link style for the HTML body (dark-blue, underlined).
_HTML_LINK_STYLE = "color:#3778be;text-decoration:underline;"
# Footer link style — same muted grey as the surrounding footer text.
_HTML_FOOTER_LINK_STYLE = "color:#b7bcbf;text-decoration:underline;"


def _md_inline(text: str, link_style: str) -> str:
    """Apply inline (no paragraph) markdown: bold, italic, links."""
    text = _MD_LINK.sub(
        lambda m: f'<a href="{m.group(2)}" style="{link_style}">{m.group(1)}</a>',
        text,
    )
    text = _MD_BOLD.sub(r"<strong>\1</strong>", text)
    text = _MD_ITALIC.sub(r"<em>\1</em>", text)
    return text


def _md_to_html(text: str) -> str:
    """Markdown → HTML for body paragraphs.

    Empty input → empty string (so a blank field doesn't emit a `<p></p>`).
    Paragraph break = blank line. Soft line breaks within a paragraph collapse
    to a single space (markdown convention).
    """
    if not text.strip():
        return ""
    paragraphs: list[str] = []
    for raw in re.split(r"\n\s*\n", text.strip()):
        chunk = re.sub(r"\s*\n\s*", " ", raw.strip())
        chunk = _md_inline(chunk, _HTML_LINK_STYLE)
        paragraphs.append(f'<p style="margin:0 0 16px 0;">{chunk}</p>')
    return "".join(paragraphs)


def _md_to_text(text: str) -> str:
    """Markdown → plain text. Preserves line + paragraph breaks."""
    if not text:
        return ""

    def link_replace(m: re.Match[str]) -> str:
        label, url = m.group(1), m.group(2)
        if label.strip() == url.strip():
            return url
        return f"{label} ({url})"

    s = _MD_LINK.sub(link_replace, text)
    s = _MD_BOLD.sub(r"\1", s)
    s = _MD_ITALIC.sub(r"\1", s)
    return s.rstrip()


def _footer_to_html(text: str) -> str:
    """Footer-flavoured HTML: line breaks → ``<br>``; no `<p>` wrappers.

    Footer styling (muted grey, smaller font, tighter line-height) lives in the
    layout's `<td>`; rendering paragraphs here would conflict with that.
    """
    if not text.strip():
        return ""
    return _md_inline(text.strip(), _HTML_FOOTER_LINK_STYLE).replace("\n", "<br>")


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render_email(cert_type: str, attendee: Attendee) -> RenderedEmail:
    """Render the email envelope for `attendee` of `cert_type`.

    Reads `conf.email.{subjects,body,footer}` for content + the shared
    `email_templates/layout.{html,txt}` for layout. Raises if any required
    field or substitution variable is missing.
    """
    # Read raw (resolve=False) so OmegaConf doesn't try to interpret the ${var}
    # placeholders in our body fields as cross-config interpolations — those
    # placeholders are for `string.Template` to substitute in the next step.
    email_conf_raw: dict[str, Any] = OmegaConf.to_container(  # type: ignore[assignment]
        conf.email, resolve=False
    )
    subject_raw = (email_conf_raw.get("subjects") or {}).get(cert_type) or ""
    body_blocks = email_conf_raw.get("body") or {}
    body_default = body_blocks.get("default") or {}
    body_type = body_blocks.get(cert_type) or {}
    # Merge: shared default ← per-type override (type wins on collision).
    body_raw: dict[str, str] = {**body_default, **body_type}
    footer_raw = email_conf_raw.get("footer") or ""
    if not subject_raw:
        raise RuntimeError(f"email.subjects.{cert_type} is not configured")
    if not body_raw:
        raise RuntimeError(f"email.body.{cert_type} (or email.body.default) is not configured")
    missing = _REQUIRED_FIELDS - set(body_raw.keys())
    if missing:
        raise RuntimeError(
            f"email.body for {cert_type} is missing field(s): {sorted(missing)}. "
            f"Set them under email.body.default or email.body.{cert_type}."
        )

    runtime_vars = _build_variables(cert_type, attendee)

    # Pass 1 — runtime-var substitution in each field + the footer.
    resolved_body = {k: Template(str(v)).substitute(runtime_vars) for k, v in body_raw.items()}
    resolved_footer = Template(str(footer_raw)).substitute(runtime_vars)

    # Pass 2 — pick the right format per layout and substitute into the shared
    # layout files.
    html_vars = dict(runtime_vars)
    text_vars = dict(runtime_vars)
    for key, value in resolved_body.items():
        if key in _PLAIN_FIELDS:
            html_vars[key] = value
            text_vars[key] = value
        else:
            html_vars[key] = _md_to_html(value)
            text_vars[key] = _md_to_text(value)
    html_vars["footer"] = _footer_to_html(resolved_footer)
    text_vars["footer"] = _md_to_text(resolved_footer)

    html_layout = (TEMPLATES_DIR / "layout.html").read_text(encoding="utf-8")
    text_layout = (TEMPLATES_DIR / "layout.txt").read_text(encoding="utf-8")

    return RenderedEmail(
        subject=Template(subject_raw).substitute(runtime_vars),
        text=Template(text_layout).substitute(text_vars),
        html=Template(html_layout).substitute(html_vars),
    )


def _build_variables(cert_type: str, attendee: Attendee) -> dict[str, str]:
    """Assemble the substitution dict. Every cert_type gets every key (empty when N/A)."""
    assert attendee.uuid
    certificates_url = (conf.get("certificates_url") or "").rstrip("/")
    download_url = f"{certificates_url}/{attendee.uuid}/{attendee.uuid}.pdf"

    validation_base = (conf.get("validation_url") or "").rstrip("/")
    validation_url = (
        f"{validation_base}/{attendee.uuid}/" if cert_type == "attendee" and validation_base else ""
    )

    speaker_url = ""
    talk_url = ""
    if cert_type == "speaker":
        speaker_cfg = conf.get("speaker") or {}
        speaker_tpl = speaker_cfg.get("speaker_url_template") or ""
        talk_tpl = speaker_cfg.get("talk_url_template") or ""
        if speaker_tpl:
            speaker_url = speaker_tpl.format(attendee=attendee)
        if talk_tpl:
            talk_url = talk_tpl.format(attendee=attendee)

    return {
        "first_name": attendee.first_name,
        "full_name": attendee.full_name,
        "event_full_name": conf.event_full_name,
        "event_short_name": conf.event_short_name,
        "certificates_url": certificates_url,
        "download_url": download_url,
        "uuid": attendee.uuid,
        "validation_url": validation_url,
        "masterclass": attendee.masterclass or "",
        "talk_title": attendee.talk_title or "",
        "speaker_url": speaker_url,
        "talk_url": talk_url,
    }
