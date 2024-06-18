import json
import secrets
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from fpdf import FPDF, FPDF_VERSION
from fpdf.enums import AccessPermission
from omegaconf import DictConfig

from src import all_fonts, logger, conf
from src.preprocess_attendees import Attendee


class PDF(FPDF):
    def __init__(self, *args, **kwargs):
        self.attendee = kwargs["attendee"]
        del kwargs["attendee"]
        super().__init__(*args, **kwargs)

    def footer(self):
        if conf.layout.footer.get("text_items"):
            for item in conf.layout.footer.text_items:
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
                text = render_text(text, attendee=self.attendee, link=conf.static_pages_website)
                self.set_x(x)
                self.set_y(y)
                self.set_text_color(77, 170, 220)
                self.multi_cell(
                    w=item.width,
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

    def __init__(self, attendees: list[Attendee],
                 event: str,
                 permissions: str | None = None,
                 sign_key: Path | None = None,
                 sign_password: bytes | None = None):
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

    def generate_certificate(self, attendee):
        fpdf = PDF(format="A4", orientation="L", unit="pt", attendee=attendee)
        self.load_project_fonts(fpdf)
        fpdf.add_page()
        if conf.layout.get("background"):
            for item in conf.layout.background:
                color = value_or_default(item, "color")
                fpdf.set_fill_color(*color)
                width = item.width if item.get("width") else fpdf.w
                height = item.height if item.get("height") else fpdf.h
                x, y = item.position if item.get("position") else (0, 0)
                fpdf.rect(x=x, y=y, w=width, h=height, style="F")

        if conf.layout.get("text_items"):
            for item in conf.layout.text_items:
                font = value_or_default(item, "font.name")
                size = value_or_default(item, "font.size")
                style = value_or_default(item, "font.style")
                color = value_or_default(item, "font.color")
                width = value_or_default(item, "width")
                text = value_or_default(item, "text")
                fpdf.set_font(font, size=size, style=style)
                # text_color = (0, 0, 0) if not item.font.get("color") else item.color.rgb
                fpdf.set_text_color(color)
                x, y = item.position if item.get("position") else (0, 0)
                text = render_text(text, attendee=attendee, event_full_name=conf.event_full_name)

                if "rotate" in item:
                    with fpdf.rotation(item.rotate, x, y):
                        fpdf.text(x=x, y=y, txt=text)
                elif "\n" in text:
                    fpdf.x, fpdf.y = x, y
                    fpdf.multi_cell(width, max_line_height=size * 1.25,
                                    text=text,
                                    markdown=True)
                else:
                    fpdf.text(x=x, y=y, txt=text)

            for g in conf.layout.graphics:
                x, y = g.position
                link = g.get("link", "")
                fpdf.image(
                    conf.dirs.graphics / g.name, x=x, y=y, w=g.width, link=link)

            fpdf.set_title(
                render_text(conf.metadata.title, attendee=attendee, event_full_name=conf.event_full_name))
            fpdf.set_subject(render_text(conf.metadata.description, attendee=attendee, event_full_name=conf.event_full_name))
            fpdf.set_author(render_text(conf.metadata.author, attendee=attendee, event_full_name=conf.event_full_name))
            fpdf.set_keywords(render_text(conf.metadata.keywords, attendee=attendee, event_full_name=conf.event_full_name))
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
