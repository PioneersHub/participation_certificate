import json
from pathlib import Path

from participation_certificate import logger
from participation_certificate.models.attendee import Attendee


class ProcessSpeakers:
    """Load the speakers JSON and flatten each (speaker, proposal) into an Attendee.

    The source is a list of speaker objects with fields:
        ID, Name, Email, Proposal IDs (list), Proposal titles (list)

    A speaker with N proposals produces N Attendee records — one cert per talk.
    """

    def __init__(self, source_path: Path):
        self.source_path = source_path
        self.attendees: list[Attendee] = self._load()

    def _load(self) -> list[Attendee]:
        data = json.loads(self.source_path.read_text(encoding="utf-8"))
        logger.info(f"Loaded {len(data)} speakers from {self.source_path}")

        attendees: list[Attendee] = []
        for speaker in data:
            full_name = (speaker.get("Name") or "").strip()
            first_name = full_name.split()[0] if full_name else ""
            email = speaker.get("Email") or ""
            speaker_id = speaker.get("ID") or ""
            proposal_ids = speaker.get("Proposal IDs") or []
            proposal_titles = speaker.get("Proposal titles") or []

            if not (full_name and email and speaker_id and proposal_ids):
                logger.warning(f"Skipping incomplete speaker record: {speaker}")
                continue

            for proposal_id, proposal_title in zip(proposal_ids, proposal_titles, strict=False):
                try:
                    attendees.append(
                        Attendee(
                            full_name=full_name,
                            first_name=first_name,
                            email=email,
                            ticket_reference=proposal_id,
                            talk_title=proposal_title,
                            speaker_id=speaker_id,
                            proposal_id=proposal_id,
                        )
                    )
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        f"Error creating speaker Attendee {full_name} ({proposal_id}): {e}"
                    )

        logger.info(f"Produced {len(attendees)} speaker certificate records.")
        return attendees
