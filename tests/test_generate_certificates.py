from pathlib import Path
import pytest
from omegaconf import OmegaConf
from unittest.mock import Mock, patch

from participation_certificate import conf
from participation_certificate.generate_certificates import PDF, Certificates, value_or_default
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
    pdf.add_font("poppins-regular", "", conf.dirs.fonts_path / "Poppins/Poppins-Regular.ttf")
    pdf.add_font("poppins-regular", "B", conf.dirs.fonts_path / "Poppins/Poppins-Bold.ttf")
    pdf.add_font("poppins-regular", "I", conf.dirs.fonts_path / "Poppins/Poppins-Italic.ttf")
    pdf.footer()
    # Check if footer content is as expected (simplified example)
    assert 28 < pdf.y < 29


def test_certificates_initialization():
    event = "Test Event"
    certificates = Certificates([attendee], event)
    assert certificates.event == event
    assert certificates.attendees == [attendee]


@patch("src.generate_certificates.PDF.output")
@patch("src.generate_certificates.Path.mkdir")
@patch("src.generate_certificates.Path.open")
def test_save_certificate(mock_open, mock_mkdir, mock_output):
    event = "Test Event"
    certificates = Certificates([attendee], event)
    mock_fpdf = Mock()
    certificates.save(attendee, mock_fpdf)
    mock_output.assert_called_once()
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


@patch("src.generate_certificates.PDF.add_page")
@patch("src.generate_certificates.Certificates.save")
def test_generate_certificate_add_page(mock_add_page, mock_save):
    event = "Test Event"
    certificates = Certificates([attendee], event)
    certificates.generate_certificate(attendee)
    mock_add_page.assert_called_once()
    mock_save.assert_called_once()


@patch("src.generate_certificates.PDF.add_page")
def test_generate_certificate_fonts(mock_add_page):
    event = "Test Event"
    certificates = Certificates([attendee], event)
    certificates.generate_certificate(attendee)
    mock_add_page.assert_called_once()
    # Check if fonts are added (simplified)
    # assert "poppins-regular" in certificates.generate_certificate(attendee).fonts


@patch("src.generate_certificates.PDF.image")
def test_generate_certificate_images(mock_image):
    event = "Test Event"
    certificates = Certificates([attendee], event)
    certificates.generate_certificate(attendee)
    assert mock_image.call_count > 0


@patch("src.generate_certificates.PDF.set_encryption")
def test_generate_certificate_encryption(mock_set_encryption):
    event = "Test Event"
    certificates = Certificates([attendee], event)
    certificates.generate_certificate(attendee)
    mock_set_encryption.assert_called_once()


@patch("src.generate_certificates.PDF.sign_pkcs12")
def test_generate_certificate_signing(mock_sign_pkcs12):
    event = "Test Event"
    sign_key = Path("/path/to/certificate")
    sign_password = b"password"
    certificates = Certificates([attendee], event, sign_key=sign_key, sign_password=sign_password)
    certificates.generate_certificate(attendee)
    mock_sign_pkcs12.assert_called_once_with(sign_key, sign_password)


test_conf = OmegaConf.create({
    'layout': {
        'default': {
            'section1': {
                'key1': 'default_value1',
                'key2': 'default_value2',
                'key8': '',
                'key4': {
                    'key5': 'default_value5',
                    'key12': '',
                },
            }},
        'section1': {
            'key1': 'value1',
            'key3': 'value2',
            'key4': '',
            'key10': '',
            'key6': {
                'key5': 'value7',
                'key11': ''
            }
        }
    }
})


class TestValueOrDefault:

    @patch("src.conf", new=test_conf)
    def test_value_present(self):
        result = value_or_default(test_conf.layout, ('section1', 'key1'))
        assert result == 'value1'
        result = value_or_default(test_conf.layout, ('section1', 'key6', 'key5'))
        assert result == 'value7'
        result = value_or_default(test_conf.layout, ('section1', 'key10'))
        assert result == ''
        result = value_or_default(test_conf.layout, ('section1', 'key6', "key11"))
        assert result == ''

    @patch("src.conf", new=test_conf)
    @patch("src.conf.layout.default", new=test_conf.layout.default)
    def test_value_missing_fallback(self):
        mock_conf = conf
        result = value_or_default(test_conf.layout, ('section1', 'key2'))
        assert result == 'default_value2'
        result = value_or_default(test_conf.layout, ('section1', 'key4', 'key5'))
        assert result == 'default_value5'
        result = value_or_default(test_conf.layout, ('section1', 'key8'))
        assert result == ''
        result = value_or_default(test_conf.layout, ('section1', 'key4', 'key12'))
        assert result == ''

    @patch("src.conf", new=test_conf)
    @patch("src.conf.layout.default", new=test_conf.layout.default)
    def test_non_existent_key(self):
        with pytest.raises(AttributeError):
            value_or_default(test_conf.layout, ('section0',))
        with pytest.raises(AttributeError):
            value_or_default(test_conf.layout, ('section1', 'key0'))
