import io
import json
import re
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

from endesive.pdf import cms
from fpdf import FPDF, FPDF_VERSION
from fpdf.enums import AccessPermission
from omegaconf import DictConfig
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

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
    ):
        """

        :param attendees: iterable of `Attendee`'s models, contains information about the person.
        :param event: Name string of the event.
        :param permissions: Defaults to allow PRINT_LOW_RES, PRINT_HIGH_RES only.
          Custom permissions can be set via `fpdf.enums.AccessPermission`.
        :param sign_key: optional: sign documents using PKCS#12 certificates; path to certificate file.
        :param sign_password: optional: only required if sign_key is set.
        """
        self.attendees: list[Attendee] = attendees
        self.event: str = event
        self.permissions: str | None = permissions
        self.sign_key: Path | None = sign_key
        self.sign_password: bytes | None = sign_password
        self.save_to = conf.dirs.path_to_certificates / self.event

    def generate_certificates(self):
        for i, attendee in enumerate(self.attendees):
            self.generate_certificate(attendee)
            logger.info(f"Saved {i}/{len(self.attendees)} certificate for {attendee.full_name}")

    def generate_certificate(self, attendee):  # noqa: PLR0915
        # Check if PDF background is configured
        use_pdf_background = (
            conf.layout.get("pdf_background")
            and isinstance(conf.layout.pdf_background, dict | DictConfig)
            and conf.layout.pdf_background.get("enabled", False)
        )

        if use_pdf_background:
            # Use pypdf/reportlab approach for PDF backgrounds
            bg_config = conf.layout.pdf_background
            bg_file = Path(conf.dirs.graphics) / bg_config.file

            if bg_file.exists():
                logger.info(f"Using PDF background for {attendee.full_name}")
                self._generate_with_pdf_background(attendee, bg_file)
            else:
                logger.error(f"Background PDF not found: {bg_file}")
                # Fallback to regular generation
                self._generate_with_colored_background(attendee)
        else:
            # Generate with colored rectangles
            self._generate_with_colored_background(attendee)

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
        # Read background PDF
        reader = PdfReader(str(bg_file))
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
                # Prepare signature metadata
                from datetime import datetime

                from cryptography.hazmat.primitives.serialization import pkcs12

                date_str = datetime.utcnow().strftime("D:%Y%m%d%H%M%S+00'00'")

                signature_dict = {
                    "sigflags": 3,
                    "contact": b"certificates@pycon.de",
                    "location": b"Digital Certificate",
                    "signingdate": date_str.encode(),
                    "reason": b"Certificate of Attendance Validation",
                    "aligned": 0,  # Auto-calculate signature size
                }

                # Load and parse the PKCS#12 certificate
                with open(self.sign_key, "rb") as p12_file:
                    p12_data = p12_file.read()

                # Extract key, cert, and additional certs from PKCS#12
                (key, cert, othercerts) = pkcs12.load_key_and_certificates(
                    p12_data, self.sign_password
                )

                # Sign the PDF
                signed_pdf_bytes = cms.sign(
                    pdf_bytes, signature_dict, key, cert, othercerts if othercerts else [], "sha256"
                )

                # Save the signed PDF
                save_to = self.save_to / f"{attendee.uuid}" / f"{attendee.uuid}.pdf"
                save_to.parent.mkdir(parents=True, exist_ok=True)

                with open(save_to, "wb") as output:
                    output.write(signed_pdf_bytes)

                logger.debug(f"Successfully signed PDF for {attendee.full_name}")

            except Exception as e:
                import traceback

                logger.error(f"Failed to sign PDF for {attendee}: {e}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                # Fallback: save unsigned PDF
                save_to = self.save_to / f"{attendee.uuid}" / f"{attendee.uuid}.pdf"
                save_to.parent.mkdir(parents=True, exist_ok=True)
                with open(save_to, "wb") as output:
                    output.write(pdf_bytes)
        else:
            # No signing - encrypt and save PDF
            logger.warning(f"NO sign_key -> NOT signing {attendee}...")

            # Apply encryption since we're not signing
            writer_encrypted = PdfReader(io.BytesIO(pdf_bytes))
            writer_final = PdfWriter()
            for page in writer_encrypted.pages:
                writer_final.add_page(page)

            # Set encryption
            owner_pwd = secrets.token_urlsafe(10)
            writer_final.encrypt(
                user_password="",  # No user password
                owner_password=owner_pwd,
                permissions_flag=(1 << 2) | (1 << 11),  # Allow printing only
            )

            save_to = self.save_to / f"{attendee.uuid}" / f"{attendee.uuid}.pdf"
            save_to.parent.mkdir(parents=True, exist_ok=True)
            with open(save_to, "wb") as output:
                writer_final.write(output)

        # Save attendee record
        json.dump(attendee.model_dump(), (save_to.parent / "record.json").open("w"), indent=4)

    def _create_text_overlay(self, attendee, page_width, page_height):
        """Create a transparent PDF with text using reportlab"""
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=(page_width, page_height))

        # Add text items from configuration
        if conf.layout.get("text_items"):
            for item in conf.layout.text_items:
                font_name = value_or_default(item, "font.name")
                size = value_or_default(item, "font.size")
                style = value_or_default(item, "font.style")
                # color = value_or_default(item, "font.color")  # Not used - white override
                text = value_or_default(item, "text")
                x, y = item.position if item.get("position") else (0, 0)

                # Render text with attendee data
                text = render_text(text, attendee=attendee, event_full_name=conf.event_full_name)

                # Convert y coordinate from top-left to bottom-left
                y_reportlab = page_height - y

                # Map font names and styles to reportlab
                reportlab_font = self._get_reportlab_font(font_name, style)
                can.setFont(reportlab_font, size)

                # Set color - override to white for visibility on dark backgrounds
                # Original color preserved in comment: color
                can.setFillColorRGB(1, 1, 1)  # White text for dark backgrounds

                # Handle rotation if specified
                if "rotate" in item:
                    can.saveState()
                    can.translate(x, y_reportlab)
                    can.rotate(item.rotate)
                    can.drawString(0, 0, text)
                    can.restoreState()
                elif "\n" in text:
                    # Multi-line text
                    lines = text.split("\n")
                    for i, line in enumerate(lines):
                        can.drawString(x, y_reportlab - (i * size * 1.25), line)
                else:
                    # Single line text
                    can.drawString(x, y_reportlab, text)

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

    def _get_reportlab_font(self, font_name, style):
        """Map fpdf font names to reportlab font names"""
        # Basic mapping - can be extended
        if "helvetica" in font_name.lower():
            base = "Helvetica"
        elif "times" in font_name.lower():
            base = "Times-Roman"
        elif "courier" in font_name.lower():
            base = "Courier"
        else:
            # Default to Helvetica for custom fonts
            # Note: Custom fonts would need to be registered with reportlab
            base = "Helvetica"

        if "B" in style and "I" in style:
            return f"{base}-BoldOblique"
        elif "B" in style:
            return f"{base}-Bold"
        elif "I" in style:
            return f"{base}-Oblique" if base == "Helvetica" else f"{base}-Italic"
        else:
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
        save_to = self.save_to / f"{attendee.uuid}" / f"{attendee.uuid}.pdf"
        save_to.parent.mkdir(parents=True, exist_ok=True)
        fpdf.output(save_to)
        json.dump(attendee.model_dump(), (save_to.parent / "record.json").open("w"), indent=4)
