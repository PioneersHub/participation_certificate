import json
import secrets
from datetime import datetime, UTC
from pathlib import Path

from fpdf import FPDF, FPDF_VERSION
from fpdf.enums import AccessPermission

from src import all_fonts, logger, conf
from src.preprocess_attendees import Attendee


class PDF(FPDF):
    def __init__(self, *args, **kwargs):
        self.attendee = kwargs["attendee"]
        del kwargs["attendee"]
        super().__init__(*args, **kwargs)

    def footer(self):
        self.set_y(-33)
        self.set_x(45)
        self.set_font("poppins-regular", size=8, style="")
        self.set_text_color(77, 170, 220)
        self.multi_cell(
            w=200,
            text=f"**[Validate this certificate online](https://2024.pycon.de/attendee-certificate/{self.attendee.uuid}/)**",
            markdown=True,
            new_x="LEFT",
            new_y="TOP",
        )


class Certificates:
    """
    Generate PDF certificates for attendees of an event.
    """

    def __init__(self, attendees: list[Attendee],
                 event: str,
                 permissions: str | None = None,
                 sign_key: Path | None = None,
                 sign_password: bytes | None = None):
        """

        :param attendees: iterable of `Attendee`'s models, contains information about the person.
        :param event: Name string of the event.
        :param permissions: defaults to allow PRINT_LOW_RES, PRINT_HIGH_RES only.
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

    def generate_certificate(self, attendee):
        fpdf = PDF(format="A4", orientation="L", unit="pt", attendee=attendee)
        self.load_project_fonts(fpdf)
        fpdf.add_page()

        fpdf.set_fill_color(61, 164, 51)
        fpdf.rect(x=0, y=0, w=fpdf.w, h=fpdf.h, style="F")

        fpdf.set_fill_color(255, 255, 255)
        fpdf.rect(x=20, y=20, w=fpdf.w - 40, h=fpdf.h - 40, style="F")

        fpdf.text(45, 98, "Certificate of Attendance")
        fpdf.set_font("poppins-bold", size=24)
        fpdf.text(50, 180, attendee.full_name)
        fpdf.text(532, 128, f"No. {attendee.hash}")
        fpdf.set_font("poppins-regular", size=14, style="")
        fpdf.text(49, 135, "This is to certify* that,")

        fpdf.x = 45
        fpdf.y = 200
        fpdf.multi_cell(600, 16.8,
                        f"has attended the **PyCon DE & PyData Berlin 2024**\n\rconference {attendee.attended_how}.",
                        markdown=True)

        fpdf.set_font("poppins-regular", size=12, style="")
        fpdf.x = 45
        fpdf.y = 256 - 14
        fpdf.multi_cell(600, 14.4,
                        # avoid unwanted word concatenations: end each line with a break or space!
                        "The annual conference covers topics in the domains of\n"
                        "Analytics, Artificial Intelligence, Community, DevOps, Ethics,\n"
                        "LLMs, Machine Learning, MLOps, Software Engineering and\n"
                        "Web Development around the Python programming\nlanguage.\n\n"
                        "The conference is run by Python Softwareverband e. V.\n"
                        "in cooperation with NumFOCUS Inc.\n\n"
                        "Signed\n\n\n\nAlexander CS Hendorf",
                        markdown=True)
        fpdf.set_font("poppins-regular", size=10, style="")
        fpdf.x = 45
        fpdf.y = 445
        fpdf.multi_cell(600, 12,
                        "as Chairman of the Board of Directors of\n"
                        "Python Softwareverband e.V.",
                        markdown=True)

        fpdf.set_font("poppins-regular", size=6, style="")
        x, y = fpdf.w - 25, 250
        with fpdf.rotation(90, x, y):
            fpdf.text(x, y, "* according to our records a named ticket was assigned to this name")

        # TODO MOVE TO config START
        gpath = Path(__file__).parents[1] / "graphics"
        fpdf.image(
            gpath / "AH-Signature.png", x=70, y=370, w=80)

        fpdf.image(
            gpath / "24-snake.svg", x=400, y=160, w=440)

        fpdf.image(
            gpath / "PySV_print_CMYK_1-1-outline+url.eps", x=45, y=500, w=75, link="https://pysv.org/")
        fpdf.image(
            gpath / "PyConDE.svg", x=125, y=500, w=40, link="https://pycon.de")
        fpdf.image(
            gpath / "NumFocus_LRG_WHITE-BG.png", x=173, y=505, w=75, link="https://numfocus.org")
        fpdf.image(
            gpath / "PyData-Berlin.svg", x=255, y=500, w=75, link="https://berlin.pydata.org")
        fpdf.image(
            gpath / "Pioneers Hub Logo.svg", x=333, y=500, w=60, link="https://pioneershub.de")

        description = """The annual conference covers topics in the domains of
        Analytics, Artificial Intelligence, Community, DevOps, Ethics, LLMs, Machine Learning, MLOps, Software Engineering and Web Development around the Python programming
        language.

        The conference is run by Python Softwareverband e. V.
        in cooperation with NumFOCUS Inc.
        """
        fpdf.set_title(f"PyCon DE & PyData Berlin 2024 - Certificate of Attendance for {attendee.full_name}")
        fpdf.set_subject(f"{description}")
        fpdf.set_author("Python Softwareverband e.V.")
        fpdf.set_keywords("PyCon DE, PyData Berlin, Python Softwareverband e.V.")
        fpdf.set_creator(f"py-pdf/fpdf{FPDF_VERSION}")
        fpdf.set_creation_date(datetime.now(UTC))
        # TODO MOVE TO config END

        fpdf.set_encryption(
            # the pdf are supposed to never be altered by anyone: we use a random, unsaved password.
            owner_password=secrets.token_urlsafe(10),
            permissions=(AccessPermission.PRINT_LOW_RES | AccessPermission.PRINT_HIGH_RES
                         if self.permissions is None else self.permissions)
        )

        if self.sign_key is not None:
            # optional
            # noinspection PyTypeChecker
            fpdf.sign_pkcs12(self.sign_key, self.sign_password)

        self.save(attendee, fpdf)

    @classmethod
    def load_project_fonts(cls, fpdf):
        for font in all_fonts:
            fpdf.add_font(font.stem.casefold(), "", font)
        fpdf.add_font("poppins-regular", "B", conf.dirs.fonts_dir / "Poppins/Poppins-Bold.ttf")
        fpdf.add_font("poppins-regular", "I", conf.dirs.fonts_dir / "Poppins/Poppins-Italic.ttf")
        fpdf.set_font("poppins-bold", size=48)

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
        json.dump(attendee.dict(), (save_to.parent / "record.json").open("w"), indent=4)
