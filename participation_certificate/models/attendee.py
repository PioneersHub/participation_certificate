import base64
import hashlib

from pydantic import UUID4, BaseModel, EmailStr


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
    """

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
    share_hash: str | None = None

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
        # public-share identifier: hash(hash). Deterministic, one-way; the share URL never
        # exposes the uuid (which is reserved for the PDF and email).
        # Encode the raw digest bytes (NOT the hex string): b64-of-hex has far reduced
        # entropy because each "byte" is just an ascii hex char, which produces frequent
        # collisions at 6 chars (observed ~1% across 2k attendees in test runs).
        hsh2 = hashlib.sha512()
        hsh2.update(self.hash.encode("utf-8"))
        self.share_hash = base64.urlsafe_b64encode(hsh2.digest())[:6].decode("utf-8").upper()
