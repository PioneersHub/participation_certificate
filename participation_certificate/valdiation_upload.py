import json
import random
from pathlib import Path

from participation_certificate import conf, logger
from participation_certificate.models.attendee import Attendee

path_to_certificates = Path(__file__).parents[1] / conf.path_to_certificates / conf.event_short_name
static_pages_website = conf.static_pages_website


def create_static_pages(replace=False):
    for record in path_to_certificates.rglob("*.json"):
        with open(record) as f:
            data = json.load(f)
            attendee = Attendee(**data)
            logger.info(
                f"Processing {attendee.full_name}->{obfuscate_name(attendee.full_name)} {attendee.uuid}"
            )
            save_to = Path(conf.static_pages_website) / attendee.uuid / "contents.lr"
            if save_to.exists() and not replace:
                continue
            save_to.parent.mkdir(parents=True, exist_ok=True)
            contents = create_md_for_page_generation(attendee, "validate_certificate")
            with open(save_to, "w") as f:
                f.write(contents)


def create_md_for_page_generation(attendee: Attendee, page_model: str):
    """
    The htmls files are generated from the markdown files.
    :param attendee: Attendee data class
    :param page_model: Page model of the website to use
    :return:
    """
    # markdown output for website
    template = f"""_model: {page_model}
---
title: Certificate of Attendance Validation Service
---
full_name: {obfuscate_name(attendee.full_name)}
---
conference: {conf.event_full_name}
---
hash: {attendee.hash}
---
_discoverable: no
    """
    return template


def obfuscate_name(name):
    words = name.split()
    obfuscated_words = []

    for word in words:
        if len(word) <= 2:
            obfuscated_words.append(word)
            continue

        # Calculate the number of characters to obfuscate
        num_chars_to_obfuscate = int(len(word) * 0.7)

        # Ensure at least one character is obfuscated and avoid obfuscating more characters than possible
        num_chars_to_obfuscate = max(1, min(num_chars_to_obfuscate, len(word) - 2))

        chars_to_obfuscate = random.sample(range(1, len(word) - 1), num_chars_to_obfuscate)

        obfuscated_word = ""
        for i, char in enumerate(word):
            if i == 0 or i == len(word) - 1 or i not in chars_to_obfuscate:
                obfuscated_word += char
            else:
                obfuscated_word += "*"

        obfuscated_words.append(obfuscated_word)

    return " ".join(obfuscated_words)


if __name__ == "__main__":
    create_static_pages()
