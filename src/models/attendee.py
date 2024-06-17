import base64
import hashlib
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from pydantic import UUID4, BaseModel, EmailStr

from src import logger


class Attendee(BaseModel):
    """
    Record to create a certificate from.
    The `hash` is created automatically from `full_name` & `ticket_reference`. It can be used as serial number on
     the certificates and to distinguish people with the same name.
    The `uuid` is created automatically and is used as a unique identifier of the certificate.
    """
    full_name: str
    first_name: str
    email: EmailStr
    ticket_reference: str
    attended_how: str
    hash: str | None = None
    uuid: str | None = None

    def model_post_init(self, ctx):  # noqa: ARG002
        # short hash to identify the attendee
        hash_this = ''.join([x.upper() for x in self.full_name if x.isalnum()]) + self.ticket_reference.strip()
        hsh = hashlib.sha512()
        hsh.update(hash_this.encode("utf-8"))
        self.hash = base64.urlsafe_b64encode(hsh.hexdigest().encode("utf-8"))[:6].decode("utf-8").upper()
        # stable uuid for webservice, this uuid will always be the same for the same attendee
        # allows reruns without cleanup
        self.uuid = str(UUID4(hsh.hexdigest()[:32]))
