import base64
import hashlib
from typing import Literal

from pydantic import UUID4, BaseModel, ConfigDict, EmailStr


class UUID(BaseModel):
    """Requirement: A UUID4 is used to name files and directories."""

    uuid: str | None = None

    def model_post_init(self, ctx):  # noqa: ARG002
        self.uuid = str(UUID4("your string here"))


# example: this is how a model for a conference attendee could look like
class Attendee(UUID):
    """
    Record to create a certificate from.
    The `hash` is created automatically from `full_name` & `ticket_reference`. It can be used as serial number on
     the certificates and to distinguish people with the same name.
    The `uuid` is created automatically and is used as a unique identifier of the certificate.

    `mail_*` fields are populated by `deliver_certificates.py` after each send;
    re-runs skip records with `mail_status == "sent"`.
    """

    # Tolerate legacy `share_hash` (and similar) keys when loading older records.
    model_config = ConfigDict(extra="ignore")

    full_name: str
    first_name: str
    email: EmailStr
    ticket_reference: str
    # Defaults so the same model serves attendee, masterclass and speaker certs.
    # Attendee uses `attended_how`; masterclass uses `masterclass`; speaker uses
    # `talk_title`, `speaker_id`, `proposal_id`.
    attended_how: str = ""
    masterclass: str | None = None
    talk_title: str | None = None
    speaker_id: str | None = None
    proposal_id: str | None = None
    hash: str | None = None
    mail_status: Literal["pending", "sent", "failed"] | None = None
    mail_message_id: str | None = None
    mail_sent_at: str | None = None
    mail_failed_at: str | None = None
    mail_last_error: str | None = None

    def model_post_init(self, ctx):  # noqa: ARG002
        # short hash to identify the attendee
        hash_this = (
            "".join([x.upper() for x in self.full_name if x.isalnum()])
            + self.ticket_reference.strip()
        )
        hsh = hashlib.sha512()
        hsh.update(hash_this.encode("utf-8"))
        # Encode the raw digest bytes (NOT the hex string) — b64-of-hex has heavily
        # reduced entropy because each "byte" is an ascii hex char, producing frequent
        # 6-char collisions (~0.7% observed across 2k attendees).
        self.hash = base64.urlsafe_b64encode(hsh.digest())[:6].decode("utf-8").upper()
        # stable uuid for webservice, this uuid will always be the same for the same attendee
        # allows reruns without cleanup
        self.uuid = str(UUID4(hsh.hexdigest()[:32]))
