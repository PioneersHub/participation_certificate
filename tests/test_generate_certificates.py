from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from omegaconf import OmegaConf
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import textobject
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from participation_certificate import conf
from participation_certificate.generate_certificates import (
    PDF,
    Certificates,
    type_subdir,
    value_or_default,
    wrapbox_baseline_draw_y,
)
from participation_certificate.preprocess_attendees import Attendee

# Sample attendee for testing
attendee = Attendee(
    first_name="John",
    full_name="John Doe",
    email="test@email.do",
    attended_how="online",
    ticket_reference="ABC-90",
)


def test_pdf_initialization():
    pdf = PDF(format="A4", orientation="L", unit="pt", attendee=attendee)
    assert pdf.attendee == attendee
    assert pdf.page == 0  # Ensuring no pages initially


def test_pdf_footer():
    pdf = PDF(format="A4", orientation="L", unit="pt", attendee=attendee)
    pdf.add_page()
    pdf.add_font("poppins-regular", "", conf.dirs.fonts_dir / "Poppins/Poppins-Regular.ttf")
    pdf.add_font("poppins-regular", "B", conf.dirs.fonts_dir / "Poppins/Poppins-Bold.ttf")
    pdf.add_font("poppins-regular", "I", conf.dirs.fonts_dir / "Poppins/Poppins-Italic.ttf")
    pdf.footer()
    # Check if footer content is as expected (simplified example)
    expected_y_min = 28
    expected_y_max = 29
    assert expected_y_min < pdf.y < expected_y_max


def test_certificates_initialization():
    event = "Test Event"
    certificates = Certificates([attendee], event)
    assert certificates.event == event
    assert certificates.attendees == [attendee]


@patch("participation_certificate.generate_certificates.write_validation_page")
@patch("participation_certificate.generate_certificates.Path.write_text")
@patch("participation_certificate.generate_certificates.Path.mkdir")
def test_save_certificate(mock_mkdir, mock_write_text, mock_write_validation):
    """save() writes the PDF to the per-uuid path and persists the JSON record
    and validation page, creating each parent directory along the way."""
    certificates = Certificates([attendee], "Test Event")
    mock_fpdf = Mock()
    certificates.save(attendee, mock_fpdf)
    mock_fpdf.output.assert_called_once_with(certificates._pdf_path(attendee))
    mock_write_text.assert_called_once()  # records/<uuid>.json
    mock_write_validation.assert_called_once()
    expected_dirs = 3  # pdf dir, record dir, validate dir
    assert mock_mkdir.call_count == expected_dirs


@patch.object(Certificates, "_generate_with_pdf_background")
@patch.object(Certificates, "_generate_with_colored_background")
def test_generate_certificate_colored_when_no_background(mock_colored, mock_pdf_bg):
    """With no PDF background configured, the colored-rectangle renderer runs."""
    certificates = Certificates([attendee], "Test Event")
    with patch.object(Certificates, "_background_file", return_value=None):
        certificates.generate_certificate(attendee)
    mock_colored.assert_called_once_with(attendee)
    mock_pdf_bg.assert_not_called()


@patch.object(Certificates, "_generate_with_pdf_background")
@patch.object(Certificates, "_generate_with_colored_background")
def test_generate_certificate_pdf_background_when_present(mock_colored, mock_pdf_bg, tmp_path):
    """A configured + existing background PDF routes to the PDF-background
    renderer, which receives the resolved path."""
    bg = tmp_path / "bg.pdf"
    bg.write_bytes(b"%PDF-1.4")
    certificates = Certificates([attendee], "Test Event")
    with patch.object(Certificates, "_background_file", return_value=bg):
        certificates.generate_certificate(attendee)
    mock_pdf_bg.assert_called_once_with(attendee, bg)
    mock_colored.assert_not_called()


def test_signing_key_threaded_to_instance():
    """The (key, password) tuple from load_signing_key() is stored for the
    renderers to sign with; omitting it yields an unsigned-cert configuration."""
    sign_key = Path("/path/to/keyStore.p12")
    sign_password = b"password"
    signed = Certificates([attendee], "E", sign_key=sign_key, sign_password=sign_password)
    assert signed.sign_key == sign_key
    assert signed.sign_password == sign_password
    unsigned = Certificates([attendee], "E")
    assert unsigned.sign_key is None
    assert unsigned.sign_password is None


test_conf = OmegaConf.create(
    {
        "layout": {
            "default": {
                "section1": {
                    "key1": "default_value1",
                    "key2": "default_value2",
                    "key8": "",
                    "key4": {
                        "key5": "default_value5",
                        "key12": "",
                    },
                }
            },
            "section1": {
                "key1": "value1",
                "key3": "value2",
                "key4": "",
                "key10": "",
                "key6": {"key5": "value7", "key11": ""},
            },
        }
    }
)


class TestValueOrDefault:
    @patch("participation_certificate.generate_certificates.conf", new=test_conf)
    def test_value_present(self):
        result = value_or_default(test_conf.layout, ("section1", "key1"))
        assert result == "value1"
        result = value_or_default(test_conf.layout, ("section1", "key6", "key5"))
        assert result == "value7"
        result = value_or_default(test_conf.layout, ("section1", "key10"))
        assert result == ""
        result = value_or_default(test_conf.layout, ("section1", "key6", "key11"))
        assert result == ""

    @patch("participation_certificate.generate_certificates.conf", new=test_conf)
    def test_value_missing_fallback(self):
        result = value_or_default(test_conf.layout, ("section1", "key2"))
        assert result == "default_value2"
        result = value_or_default(test_conf.layout, ("section1", "key4", "key5"))
        assert result == "default_value5"
        result = value_or_default(test_conf.layout, ("section1", "key8"))
        assert result == ""
        result = value_or_default(test_conf.layout, ("section1", "key4", "key12"))
        assert result == ""

    @patch("participation_certificate.generate_certificates.conf", new=test_conf)
    def test_non_existent_key(self):
        with pytest.raises(AttributeError):
            value_or_default(test_conf.layout, ("section0",))
        with pytest.raises(AttributeError):
            value_or_default(test_conf.layout, ("section1", "key0"))


@pytest.mark.parametrize(
    ("cert_type", "expected"),
    [
        ("attendee", "attendees"),
        ("speaker", "speakers"),
        ("volunteer", "volunteers"),
        ("masterclass", "masterclasses"),  # sibilant ending -> "es", not "masterclasss"
    ],
)
def test_type_subdir_pluralises(cert_type, expected):
    """Output subdir is the pluralised cert-type token (sibilant endings take 'es')."""
    assert type_subdir(cert_type) == expected


def _capture_first_baseline(para, draw_x, draw_y, page_size=(842, 595)):
    """Render `para` at (draw_x, draw_y) on a real reportlab canvas and return
    the absolute y of the first text baseline reportlab actually emits.

    Spies on the (reportlab-internal) text-object origin call so the assertion
    reflects real line placement, not a re-derivation of our own formula.
    """
    captured = {}
    original = textobject.PDFTextObject.setTextOrigin

    def spy(self, x, y):
        captured.setdefault("y", self._canvas._currentMatrix[5] + y)
        return original(self, x, y)

    textobject.PDFTextObject.setTextOrigin = spy
    try:
        para.drawOn(Canvas(BytesIO(), pagesize=page_size), draw_x, draw_y)
    finally:
        textobject.PDFTextObject.setTextOrigin = original
    return captured["y"]


def test_wrapbox_first_baseline_matches_simple_text_baseline():
    """Unified convention: a single-line wrap-box item and a simple text item at
    the same [x, y] share a baseline. A simple item renders its baseline at
    `page_height - y` (drawString); the wrap-box must land there too."""
    page_height, x, y, size = 595, 160, 135, 16
    style = ParagraphStyle(
        name="cell", fontName="Helvetica-Bold", fontSize=size, leading=size * 1.2
    )
    para = Paragraph("A short talk title", style)
    _w, para_h = para.wrap(450, 60)

    draw_y = wrapbox_baseline_draw_y(page_height, y, para_h, size)
    baseline = _capture_first_baseline(para, x, draw_y)

    assert baseline == pytest.approx(page_height - y, abs=0.5)
