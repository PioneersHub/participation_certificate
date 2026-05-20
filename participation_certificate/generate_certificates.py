import io
import json
import re
import secrets
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.serialization import pkcs12
from endesive.pdf import cms
from fpdf import FPDF, FPDF_VERSION
from fpdf.enums import AccessPermission
from omegaconf import DictConfig
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from participation_certificate import all_fonts, conf, logger
from participation_certificate.preprocess_attendees import Attendee


class PDF(FPDF):
    def __init__(self, *args, **kwargs):
        self.attendee = kwargs["attendee"]
        del kwargs["attendee"]
        super().__init__(*args, **kwargs)

    def footer(self):
        footer_config = conf.layout.get("footer", {}).get("text_items")
        if not footer_config:
            return
        for item in footer_config:
            font = value_or_default(item, "font.name")
            size = value_or_default(item, "font.size")
            style = value_or_default(item, "font.style")
            color = value_or_default(item, "font.color")
            width = value_or_default(item, "width")
            text = value_or_default(item, "text")
            self.set_font(font, size=size, style=style)
            # text_color = (0, 0, 0) if not item.font.get("color") else item.color.rgb
            self.set_text_color(color)
            x, y = item.position
            # Use validation_url if available, otherwise fall back to static_pages_website
            link_url = conf.get("validation_url", conf.static_pages_website)
            text = render_text(text, attendee=self.attendee, link=link_url)
            self.set_x(x)
            self.set_y(y)
            self.set_text_color(77, 170, 220)
            self.multi_cell(
                w=width,
                text=text,
                markdown=True,
                new_x="LEFT",
                new_y="TOP",
            )


def value_or_default(obj: DictConfig, keys: tuple[str, ...] | str, path: tuple[str, ...] = ()):
    if isinstance(keys, str):
        keys = tuple(keys.split("."))
    for key in keys:
        if "default" in path and "default" in obj:
            obj = obj.default
        if key in obj:
            if keys[1:]:
                path = path + (key,)
                return value_or_default(obj[key], keys=keys[1:], path=path)
            return obj[key]
        elif "default" in path:
            raise AttributeError(f"Default value {'.'.join(path + (key,))} does not exist.")
        else:
            return value_or_default(conf.layout, keys=path + keys, path=("default",))


# Words with this many characters or fewer are kept verbatim by `obfuscate_name`.
_OBFUSCATION_MIN_WORD_LEN = 3
# Length of an RGB colour triple in our config representation.
_RGB_TRIPLE_LEN = 3


def obfuscate_name(full_name: str) -> str:
    """Deterministic asterisk obfuscation for public validation/share pages.

    Keep first and last char of each word; replace everything in between with '*'.
    Words shorter than `_OBFUSCATION_MIN_WORD_LEN` are left unchanged. Same input
    → same output every time, so Lektor rebuilds don't churn the published page.

    "Mateusz Sokół" -> "M*****z S***ł"
    "Ga Man Liang"  -> "Ga M*n L***g"
    """
    out = []
    for word in full_name.split():
        if len(word) < _OBFUSCATION_MIN_WORD_LEN:
            out.append(word)
        else:
            out.append(word[0] + "*" * (len(word) - 2) + word[-1])
    return " ".join(out)


def _type_conf(cert_type: str):
    """Return the per-type config block. Attendee defaults to the top-level config."""
    if cert_type == "attendee":
        return conf
    return conf.get(cert_type) or {}


# Cert-type → on-disk subdir under <event>/. Singular tokens are the programmatic
# identifiers; plural names are the output directory layout the user expects:
#   _certificates/<event>/{attendees, masterclasses, speakers}/...
_TYPE_SUBDIR = {
    "attendee": "attendees",
    "masterclass": "masterclasses",
    "speaker": "speakers",
}


def type_subdir(cert_type: str) -> str:
    """Return the per-type output sub-directory name."""
    return _TYPE_SUBDIR.get(cert_type, cert_type)


def write_validation_page(
    attendee: Attendee, target_dir: Path, cert_type: str = "attendee"
) -> None:
    """Write the slim Lektor `contents.lr` validation page (UUID-keyed, attendee-only).

    Only attendee certs get a validation page — masterclass and speaker certs
    are delivered solely by email, never published to the PyCon website.
    """
    title = conf.get("validation_page_title") or "Certificate of Attendance Validation Service"
    blocks = [
        "_model: validate_certificate",
        f"title: {title}",
        f"full_name: {obfuscate_name(attendee.full_name)}",
        f"conference: {conf.event_full_name}",
        f"hash: {attendee.hash}",
        f"cert_type: {cert_type}",
        "_discoverable: no",
    ]
    contents = "\n---\n".join(blocks) + "\n"
    (target_dir / "contents.lr").write_text(contents, encoding="utf-8")


def _to_reportlab_color(color, alpha=None) -> Color:
    """Build a reportlab `Color` from our config form (RGB 0–255 list/tuple or int)."""
    a = 1 if alpha is None else alpha
    if isinstance(color, list | tuple) and len(color) == _RGB_TRIPLE_LEN:
        return Color(color[0] / 255, color[1] / 255, color[2] / 255, alpha=a)
    if isinstance(color, int | float):
        g = color / 255
        return Color(g, g, g, alpha=a)
    return Color(0, 0, 0, alpha=a)


def render_text(text: str | list, **kwargs):
    new_text = []
    if isinstance(text, str):
        new_text.append(text.format(**kwargs))
    else:
        for line in text:
            new_text.append(line.format(**kwargs))
    return "\n".join(new_text)


class Certificates:
    """
    Generate PDF certificates for attendees of an event.
    """

    def __init__(  # noqa: PLR0913
        self,
        attendees: list[Attendee],
        event: str,
        permissions: str | None = None,
        sign_key: Path | None = None,
        sign_password: bytes | None = None,
        cert_type: str = "attendee",
    ):
        """

        :param attendees: iterable of `Attendee`'s models, contains information about the person.
        :param event: Name string of the event.
        :param permissions: Defaults to allow PRINT_LOW_RES, PRINT_HIGH_RES only.
          Custom permissions can be set via `fpdf.enums.AccessPermission`.
        :param sign_key: optional: sign documents using PKCS#12 certificates; path to certificate file.
        :param sign_password: optional: only required if sign_key is set.
        :param cert_type: "attendee" (default, top-level config), "masterclass", or "speaker".
          Non-attendee types live under their own config block and their own output sub-tree.
        """
        self.attendees: list[Attendee] = attendees
        self.event: str = event
        self.permissions: str | None = permissions
        self.sign_key: Path | None = sign_key
        self.sign_password: bytes | None = sign_password
        self.cert_type: str = cert_type
        # All cert types live under their own pluralised sub-directory.
        # `path_to_certificates` is already project-scoped (resolved against
        # PROJECT_DIR in participation_certificate/__init__.py), so we do NOT
        # add another <event> middle component here.
        self.save_to = conf.dirs.path_to_certificates / type_subdir(cert_type)
        # Cached background-PDF bytes, keyed by absolute path. Reading the same
        # multi-megabyte file once per attendee was burning ~10 % of the wall
        # time on a 2k-cert run; cache once + reparse from memory.
        self._bg_cache: dict[Path, bytes] = {}

    def _bg_bytes(self, bg_file: Path) -> bytes:
        """Return the background PDF bytes, reading from disk only the first time."""
        cached = self._bg_cache.get(bg_file)
        if cached is None:
            cached = bg_file.read_bytes()
            self._bg_cache[bg_file] = cached
        return cached

    def _type_conf(self):
        """Per-type config block. Returns the top-level conf for attendee, conf[cert_type] otherwise."""
        if self.cert_type == "attendee":
            return conf
        return conf.get(self.cert_type) or {}

    # Output layout (under self.save_to):
    #   upload-to-certificates/<uuid>/<uuid>.pdf   — signed PDF (emailed as attachment)
    #   records/<uuid>.json                        — full Attendee dump + mail_status
    #   website-validate/<uuid>/contents.lr        — Lektor validation page (attendee only)
    def _pdf_path(self, attendee):
        return self.save_to / "upload-to-certificates" / attendee.uuid / f"{attendee.uuid}.pdf"

    def _record_path(self, attendee):
        return self.save_to / "records" / f"{attendee.uuid}.json"

    def _validate_dir(self, attendee):
        return self.save_to / "website-validate" / attendee.uuid

    def generate_certificates(self):
        for i, attendee in enumerate(self.attendees):
            self.generate_certificate(attendee)
            logger.info(f"Saved {i}/{len(self.attendees)} certificate for {attendee.full_name}")

    def generate_certificate(self, attendee):  # noqa: PLR0915
        bg_file = self._background_file()
        if bg_file is not None:
            if not bg_file.exists():
                # A background is configured but the file is missing. For the
                # attendee path, fall back to the legacy colored-rect renderer
                # to preserve old behaviour; for masterclass/speaker, fail fast
                # — those types are only meaningful with their event background.
                if self.cert_type == "attendee":
                    logger.error(f"Background PDF not found: {bg_file} — falling back.")
                    self._generate_with_colored_background(attendee)
                    return
                raise FileNotFoundError(
                    f"{self.cert_type} background PDF not found: {bg_file}. "
                    f"Provide the file or disable conf.{self.cert_type}.enabled."
                )
            logger.info(f"Using PDF background for {attendee.full_name}")
            self._generate_with_pdf_background(attendee, bg_file)
        else:
            self._generate_with_colored_background(attendee)

    def _background_file(self) -> Path | None:
        """Return the PDF-background path for this cert type, or None if not configured."""
        if self.cert_type == "attendee":
            bg = conf.layout.get("pdf_background")
            if (
                bg
                and isinstance(bg, dict | DictConfig)
                and bg.get("enabled", False)
                and bg.get("file")
            ):
                return Path(conf.dirs.graphics) / bg["file"]
            return None
        # masterclass / speaker: background lives under the per-type block.
        type_conf = self._type_conf()
        bg = type_conf.get("pdf_background") if type_conf else None
        if bg and isinstance(bg, dict | DictConfig) and bg.get("file"):
            return Path(conf.dirs.graphics) / bg["file"]
        return None

    def _generate_with_colored_background(self, attendee):
        """Generate certificate with colored rectangle backgrounds using fpdf2"""
        fpdf = PDF(format="A4", orientation="L", unit="pt", attendee=attendee)
        self.load_project_fonts(fpdf)
        fpdf.add_page()

        if conf.layout.get("background"):
            # Add colored rectangle backgrounds
            for item in conf.layout.background:
                color = value_or_default(item, "color")
                fpdf.set_fill_color(*color)
                width = item.width if item.get("width") else fpdf.w
                height = item.height if item.get("height") else fpdf.h
                x, y = item.position if item.get("position") else (0, 0)
                fpdf.rect(x=x, y=y, w=width, h=height, style="F")

        # Add all content (text, graphics, etc.)
        self._add_content_to_pdf(fpdf, attendee)

        # Save the certificate
        self.save(attendee, fpdf)

    def _generate_with_pdf_background(self, attendee, bg_file):  # noqa: PLR0915
        """Generate certificate with PDF background using pypdf/reportlab"""
        # Read background PDF from cached bytes (one disk read per Certificates instance).
        reader = PdfReader(io.BytesIO(self._bg_bytes(bg_file)))
        background_page = reader.pages[0]

        # Get page dimensions
        page_width = float(background_page.mediabox.width)
        page_height = float(background_page.mediabox.height)

        # Create overlay with text using reportlab
        overlay_bytes = self._create_text_overlay(attendee, page_width, page_height)

        # Merge overlay with background
        overlay_reader = PdfReader(overlay_bytes)
        overlay_page = overlay_reader.pages[0]
        background_page.merge_page(overlay_page)

        # Create writer and add merged page
        writer = PdfWriter()
        writer.add_page(background_page)

        # Add metadata
        writer.add_metadata(
            {
                "/Title": render_text(
                    conf.metadata.title, attendee=attendee, event_full_name=conf.event_full_name
                ),
                "/Subject": render_text(
                    conf.metadata.description,
                    attendee=attendee,
                    event_full_name=conf.event_full_name,
                ),
                "/Author": render_text(
                    conf.metadata.author, attendee=attendee, event_full_name=conf.event_full_name
                ),
                "/Keywords": render_text(
                    conf.metadata.keywords, attendee=attendee, event_full_name=conf.event_full_name
                ),
                "/Creator": f"py-pdf/fpdf{FPDF_VERSION} with pypdf/reportlab",
            }
        )

        # Get PDF bytes BEFORE encryption for signing
        pdf_buffer = io.BytesIO()
        writer.write(pdf_buffer)
        pdf_buffer.seek(0)
        pdf_bytes = pdf_buffer.read()

        # Digital signing with endesive if certificate is provided
        if self.sign_key is not None:
            logger.info(f"Signing {attendee}...")
            try:
                # Format as PDF signing date per PDF reference (D:YYYYMMDDHHmmSS+00'00').
                date_str = datetime.now(UTC).strftime("D:%Y%m%d%H%M%S+00'00'")

                signing_conf = conf.get("signing") or {}
                signature_dict = {
                    "sigflags": 3,
                    "contact": (signing_conf.get("contact") or "").encode(),
                    "location": (signing_conf.get("location") or "").encode(),
                    "signingdate": date_str.encode(),
                    "reason": (signing_conf.get("reason") or "").encode(),
                    "aligned": 16384,  # Reserve enough bytes for the signature
                }

                # Load and parse the PKCS#12 certificate
                with open(self.sign_key, "rb") as p12_file:
                    p12_data = p12_file.read()

                # Extract key, cert, and additional certs from PKCS#12
                (key, cert, othercerts) = pkcs12.load_key_and_certificates(
                    p12_data, self.sign_password
                )

                # endesive.pdf.cms.sign returns only the incremental-update
                # appendix; it must be concatenated to the original PDF bytes.
                signature_appendix = cms.sign(
                    pdf_bytes, signature_dict, key, cert, othercerts if othercerts else [], "sha256"
                )
                signed_pdf_bytes = pdf_bytes + signature_appendix

                pdf_path = self._pdf_path(attendee)
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                with open(pdf_path, "wb") as output:
                    output.write(signed_pdf_bytes)

                logger.debug(f"Successfully signed PDF for {attendee.full_name}")

            except Exception as e:
                logger.error(f"Failed to sign PDF for {attendee}: {e}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                # Fallback: save unsigned PDF
                pdf_path = self._pdf_path(attendee)
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                with open(pdf_path, "wb") as output:
                    output.write(pdf_bytes)
        else:
            # No signing - encrypt and save PDF
            logger.warning(f"NO sign_key -> NOT signing {attendee}...")

            writer_encrypted = PdfReader(io.BytesIO(pdf_bytes))
            writer_final = PdfWriter()
            for page in writer_encrypted.pages:
                writer_final.add_page(page)

            owner_pwd = secrets.token_urlsafe(10)
            writer_final.encrypt(
                user_password="",  # No user password
                owner_password=owner_pwd,
                permissions_flag=(1 << 2) | (1 << 11),  # Allow printing only
            )

            pdf_path = self._pdf_path(attendee)
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pdf_path, "wb") as output:
                writer_final.write(output)

        # Save attendee record (flat under records/<uuid>.json).
        record_path = self._record_path(attendee)
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(
            json.dumps(attendee.model_dump(), indent=4, ensure_ascii=False),
            encoding="utf-8",
        )

        # Validation Lektor page — only attendees get published on 2026.pycon.de.
        # Masterclass + speaker certs are delivered solely by email.
        if self.cert_type == "attendee":
            validate_dir = self._validate_dir(attendee)
            validate_dir.mkdir(parents=True, exist_ok=True)
            write_validation_page(attendee, validate_dir, self.cert_type)

    def _create_text_overlay(self, attendee, page_width, page_height):  # noqa: PLR0912, PLR0915
        """Create a transparent PDF with text using reportlab.

        Renders every configured text item onto the cert background.
        """
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=(page_width, page_height))

        # Add text items from configuration.
        # For attendee: text_items live under conf.layout. For masterclass/speaker:
        # under conf.<cert_type>.text_items so each type has its own overlay.
        validation_url = conf.get("validation_url") or conf.get("static_pages_website", "")
        attendance_map = conf.get("attendance_display") or {}
        attended_how_display = attendance_map.get(attendee.attended_how, "")

        # Speaker URL templates resolve against the attendee record; empty for other types.
        speaker_conf = conf.get("speaker") or {}
        speaker_url_tpl = speaker_conf.get("speaker_url_template") or ""
        talk_url_tpl = speaker_conf.get("talk_url_template") or ""
        speaker_url = speaker_url_tpl.format(attendee=attendee) if speaker_url_tpl else ""
        talk_url = talk_url_tpl.format(attendee=attendee) if talk_url_tpl else ""

        if self.cert_type == "attendee":
            text_items = conf.layout.get("text_items") or []
        else:
            type_conf = self._type_conf()
            text_items = (type_conf.get("text_items") or []) if type_conf else []

        for item in text_items:
            font_name = value_or_default(item, "font.name")
            size = value_or_default(item, "font.size")
            style = value_or_default(item, "font.style")
            color = value_or_default(item, "font.color")
            alpha = item.get("font", {}).get("alpha") if item.get("font") else None
            text = value_or_default(item, "text")
            x, y = item.position if item.get("position") else (0, 0)

            # Render text with attendee data
            text = render_text(
                text,
                attendee=attendee,
                event_full_name=conf.event_full_name,
                validation_url=validation_url,
                attended_how_display=attended_how_display,
                speaker_url=speaker_url,
                talk_url=talk_url,
            )

            # Convert y coordinate from top-left to bottom-left
            y_reportlab = page_height - y

            # Map font names and styles to reportlab
            reportlab_font = self._get_reportlab_font(font_name, style)
            can.setFont(reportlab_font, size)

            # Apply configured color (RGB 0-255 list/tuple, or grayscale int).
            # Optional `font.alpha` (0..1) makes watermarks semi-transparent.
            if isinstance(color, list | tuple) and len(color) == _RGB_TRIPLE_LEN:
                can.setFillColorRGB(color[0] / 255, color[1] / 255, color[2] / 255, alpha=alpha)
            elif isinstance(color, int | float):
                g = color / 255
                can.setFillColorRGB(g, g, g, alpha=alpha)
            else:
                can.setFillColorRGB(0, 0, 0, alpha=alpha)

            # Detect markdown link: [visible text](url) -> render as blue underlined link
            md_link = re.match(r"^\[([^\]]+)\]\(([^)]+)\)$", text)

            # Wrap-box rendering: when both `width` and `height` are set, use a
            # reportlab Paragraph so the text wraps inside the box (max `width`)
            # and is vertically centred within `height`. Markdown links are
            # preserved as clickable links via the Paragraph's `<a>` markup.
            box_width = item.get("width")
            box_height = item.get("height")
            if box_width and box_height:
                align_map = {"left": 0, "center": 1, "centre": 1, "right": 2}
                style_obj = ParagraphStyle(
                    name="cell",
                    fontName=reportlab_font,
                    fontSize=size,
                    leading=size * 1.2,
                    textColor=_to_reportlab_color(color, alpha),
                    alignment=align_map.get(item.get("align"), 0),
                )
                if md_link:
                    link_text, link_url = md_link.group(1), md_link.group(2)
                    para_html = f'<a href="{link_url}"><u>{link_text}</u></a>'
                else:
                    para_html = text
                para = Paragraph(para_html, style_obj)
                _w, para_h = para.wrap(box_width, box_height)
                # Vertically centre inside the box; `y` is the box's top edge in
                # top-left coords, so box-bottom in reportlab coords is below.
                box_bottom_rl = page_height - (y + box_height)
                y_offset = (box_height - para_h) / 2
                para.drawOn(can, x, box_bottom_rl + y_offset)
                continue

            if md_link:
                link_text, link_url = md_link.group(1), md_link.group(2)
                draw = self._aligned_drawer(can, item.get("align"))
                draw(x, y_reportlab, link_text)
                text_w = can.stringWidth(link_text, reportlab_font, size)
                # For right-aligned text, the underline + link box start at (x - text_w).
                left = x - text_w if item.get("align") == "right" else x
                can.setLineWidth(0.5)
                can.line(left, y_reportlab - 1, left + text_w, y_reportlab - 1)
                can.linkURL(
                    link_url,
                    (left, y_reportlab - 2, left + text_w, y_reportlab + size),
                    relative=0,
                )
            elif "rotate" in item:
                can.saveState()
                can.translate(x, y_reportlab)
                can.rotate(item.rotate)
                can.drawString(0, 0, text)
                can.restoreState()
            elif "\n" in text:
                # Multi-line text
                draw = self._aligned_drawer(can, item.get("align"))
                lines = text.split("\n")
                for i, line in enumerate(lines):
                    draw(x, y_reportlab - (i * size * 1.25), line)
            else:
                # Single line text
                self._aligned_drawer(can, item.get("align"))(x, y_reportlab, text)

        # Add footer if configured
        footer_config = conf.layout.get("footer", {}).get("text_items")
        if footer_config:
            for item in footer_config:
                font_name = value_or_default(item, "font.name")
                size = value_or_default(item, "font.size")
                # color = value_or_default(item, "font.color")  # Not used - white override
                text = value_or_default(item, "text")
                x, y = item.position

                # Handle negative y (from bottom)
                y_reportlab = abs(y) if y < 0 else page_height - y

                link_url = conf.get("validation_url", conf.static_pages_website)
                text = render_text(text, attendee=attendee, link=link_url)

                # Remove markdown formatting for now
                text = text.replace("**[", "").replace(
                    "](" + link_url + "/" + attendee.uuid + "/)**", ""
                )

                reportlab_font = self._get_reportlab_font(font_name, "")
                can.setFont(reportlab_font, size)
                can.setFillColorRGB(1, 1, 1)  # White text for visibility
                can.drawString(x, y_reportlab, text)

                # Add link annotation
                full_url = f"{link_url}/{attendee.uuid}/"
                can.linkURL(full_url, (x, y_reportlab - 5, x + 200, y_reportlab + 10), relative=0)

        # Note: Graphics would need to be handled differently with reportlab
        # For now, we'll skip graphics as they're in the background PDF

        can.save()
        packet.seek(0)
        return packet

    @staticmethod
    def _aligned_drawer(can, align):
        """Return the reportlab canvas method matching `align` (left/right/center)."""
        if align == "right":
            return can.drawRightString
        if align in ("center", "centre"):
            return can.drawCentredString
        return can.drawString

    _registered_ttf: set = set()

    def _register_reportlab_ttf(self, font_name, style):
        """Register the configured TTF with reportlab if available; return its name or None.

        Built-in PostScript fonts (Helvetica/Times/Courier) use WinAnsiEncoding and cannot
        render characters outside Latin-1 (e.g. Polish ł, ś, ż). TTF fonts registered via
        reportlab.pdfbase.ttfonts.TTFont use the font's own Unicode cmap, so they render
        correctly.
        """
        variant = "bold" if "B" in style else "italic" if "I" in style else "regular"
        cache_key = (font_name.lower(), variant)
        reg_name = f"{font_name}-{variant}"

        if cache_key in self._registered_ttf:
            return reg_name

        custom_fonts = conf.fonts.get("custom_fonts") if conf.get("fonts") else None
        family = custom_fonts.get(font_name) if custom_fonts else None
        if not family:
            return None

        rel_path = family.get(variant) or family.get("regular")
        if not rel_path:
            return None

        font_path = Path(conf.dirs.fonts_dir) / rel_path
        if not font_path.exists():
            logger.warning(f"Configured font not found on disk: {font_path}")
            return None

        try:
            pdfmetrics.registerFont(TTFont(reg_name, str(font_path)))
        except TTFError as exc:
            logger.warning(f"Failed to register TTF {font_path}: {exc}")
            return None

        self._registered_ttf.add(cache_key)
        return reg_name

    def _get_reportlab_font(self, font_name, style):
        """Return a reportlab font name. Prefer registered TTFs (full Unicode); else Helvetica."""
        if font_name:
            registered = self._register_reportlab_ttf(font_name, style)
            if registered:
                return registered

        if font_name and "times" in font_name.lower():
            base = "Times-Roman"
        elif font_name and "courier" in font_name.lower():
            base = "Courier"
        else:
            base = "Helvetica"

        if "B" in style and "I" in style:
            return f"{base}-BoldOblique" if base == "Helvetica" else f"{base}-BoldItalic"
        if "B" in style:
            return f"{base}-Bold"
        if "I" in style:
            return f"{base}-Oblique" if base == "Helvetica" else f"{base}-Italic"
        return base

    def _add_content_to_pdf(self, fpdf, attendee):  # noqa: PLR0915
        """Add text items, graphics, and metadata to the PDF"""
        if conf.layout.get("text_items"):
            for item in conf.layout.text_items:
                font = value_or_default(item, "font.name")
                size = value_or_default(item, "font.size")
                style = value_or_default(item, "font.style")
                color = value_or_default(item, "font.color")
                width = value_or_default(item, "width")
                text = value_or_default(item, "text")
                fpdf.set_font(font, size=size, style=style)
                fpdf.set_text_color(*color) if isinstance(
                    color, list | tuple
                ) else fpdf.set_text_color(color)
                x, y = item.position if item.get("position") else (0, 0)
                text = render_text(text, attendee=attendee, event_full_name=conf.event_full_name)

                # Check if this is a markdown link
                is_markdown_link = "](http" in text and "[" in text

                if "rotate" in item:
                    with fpdf.rotation(item.rotate, x, y):
                        fpdf.text(x=x, y=y, txt=text)
                elif is_markdown_link:
                    # For markdown links, use cell with link which survives PDF merging better
                    # Extract link text and URL from markdown
                    match = re.search(r"\*?\*?\[([^\]]+)\]\(([^)]+)\)\*?\*?", text)
                    if match:
                        link_text = match.group(1)
                        link_url = match.group(2)
                        logger.debug(f"Adding link: {link_text} -> {link_url}")
                        fpdf.set_xy(x, y)
                        # Save current font settings
                        current_style = style
                        # Add underline for link appearance
                        fpdf.set_font(font, size=size, style="U")
                        # Use cell with link parameter which is more reliable
                        fpdf.cell(text=link_text, link=link_url)
                        # Restore original font style
                        fpdf.set_font(font, size=size, style=current_style)
                    else:
                        logger.warning(f"Failed to parse markdown link: {text}")
                        # Fallback to multi_cell if parsing fails
                        fpdf.x, fpdf.y = x, y
                        fpdf.multi_cell(
                            width, max_line_height=size * 1.25, text=text, markdown=True
                        )
                elif "\n" in text:  # Multi-line text
                    fpdf.x, fpdf.y = x, y
                    fpdf.multi_cell(width, max_line_height=size * 1.25, text=text, markdown=True)
                else:
                    fpdf.text(x=x, y=y, txt=text)

        if conf.layout.get("graphics"):
            for g in conf.layout.graphics:
                x, y = g.position
                link = g.get("link", "")
                fpdf.image(conf.dirs.graphics / g.name, x=x, y=y, w=g.width, link=link)

        # Set metadata
        fpdf.set_title(
            render_text(
                conf.metadata.title, attendee=attendee, event_full_name=conf.event_full_name
            )
        )
        fpdf.set_subject(
            render_text(
                conf.metadata.description,
                attendee=attendee,
                event_full_name=conf.event_full_name,
            )
        )
        fpdf.set_author(
            render_text(
                conf.metadata.author, attendee=attendee, event_full_name=conf.event_full_name
            )
        )
        fpdf.set_keywords(
            render_text(
                conf.metadata.keywords, attendee=attendee, event_full_name=conf.event_full_name
            )
        )
        fpdf.set_creator(f"py-pdf/fpdf{FPDF_VERSION}")
        fpdf.set_creation_date(datetime.now(UTC))

        fpdf.set_encryption(
            # the pdf are supposed to never be altered by anyone: we use a random, unsaved password.
            owner_password=secrets.token_urlsafe(10),
            permissions=(
                AccessPermission.PRINT_LOW_RES | AccessPermission.PRINT_HIGH_RES
                if self.permissions is None
                else self.permissions
            ),
        )

        if self.sign_key is not None:
            # optional
            # noinspection PyTypeChecker
            logger.info(f"Signing {attendee}...")
            fpdf.sign_pkcs12(self.sign_key, self.sign_password)
        else:
            logger.warning(f"NO sign_key -> NOT signing {attendee}...")

    @classmethod
    def load_project_fonts(cls, fpdf):
        """Load fonts based on configuration"""
        fonts_config = conf.get("fonts", {})

        # Get list of custom font families to skip in auto-load
        custom_fonts = fonts_config.get("custom_fonts", {})
        custom_font_names = set(custom_fonts.keys())

        # Auto-load all TTF fonts if enabled (skip those in custom_fonts)
        if fonts_config.get("auto_load_ttf", True):
            for font in all_fonts:
                font_name = font.stem.casefold()
                # Skip fonts that will be loaded via custom_fonts
                if font_name not in custom_font_names and not any(
                    font_name.startswith(cf) for cf in custom_font_names
                ):
                    cls._add_font_safe(fpdf, font_name, "", font)

        # Load custom fonts from configuration (these take priority)
        style_map = {"regular": "", "bold": "B", "italic": "I", "bold_italic": "BI"}

        for font_family, font_paths in custom_fonts.items():
            if not isinstance(font_paths, dict | DictConfig):
                continue

            for variant, style in style_map.items():
                if variant in font_paths:
                    font_path = conf.dirs.fonts_dir / font_paths[variant]
                    cls._add_font_safe(fpdf, font_family, style, font_path)

        # Set initial font from configuration
        initial = fonts_config.get("initial_font", {})
        cls._set_font_safe(
            fpdf,
            initial.get("name", fonts_config.get("default_font", "helvetica")),
            initial.get("style", ""),
            initial.get("size", fonts_config.get("default_size", 12)),
        )

    @classmethod
    def _add_font_safe(cls, fpdf, family, style, path):
        """Safely add a font with error handling"""
        if Path(path).exists():
            try:
                # Suppress warnings for .ttc files with Mac-specific tables
                if str(path).endswith(".ttc"):
                    old_stderr = sys.stderr
                    sys.stderr = io.StringIO()
                    try:
                        fpdf.add_font(family, style, path)
                    finally:
                        sys.stderr = old_stderr
                else:
                    fpdf.add_font(family, style, path)

                variant = {"": "regular", "B": "bold", "I": "italic", "BI": "bold-italic"}.get(
                    style, style
                )
                logger.debug(f"Loaded {family} {variant} from {path}")
            except Exception as e:
                logger.warning(f"Could not load {family} {style}: {e}")

    @classmethod
    def _set_font_safe(cls, fpdf, name, style, size):
        """Safely set font with fallback to helvetica"""
        try:
            fpdf.set_font(name, style=style, size=size)
            logger.debug(f"Set initial font: {name} {style} {size}pt")
        except Exception as e:
            logger.warning(f"Could not set font {name}: {e}, using helvetica")
            fpdf.set_font("helvetica", size=size)

    def save(self, attendee: Attendee, fpdf):
        """
        Save the certificate to disk accompanied by a json file with the data of `Attendee` for later use:
          - email address to send the notification to
          - Name
        :param attendee: Attendee model
        :param fpdf: instance of `FPDF` with the certificate
        :return:
        """
        pdf_path = self._pdf_path(attendee)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        fpdf.output(pdf_path)

        record_path = self._record_path(attendee)
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(
            json.dumps(attendee.model_dump(), indent=4, ensure_ascii=False),
            encoding="utf-8",
        )

        validate_dir = self._validate_dir(attendee)
        validate_dir.mkdir(parents=True, exist_ok=True)
        write_validation_page(attendee, validate_dir, self.cert_type)
