"""Build Attendee records for speaker certificates.

Two source files are required, both under `_data/`:

  * `<sessions_json>` — confirmed sessions only (the source of truth for which
    certs to emit). Schema per item:
        {"ID", "Proposal title", "Session type": {"en": ...},
         "Speaker IDs": [...], "Speaker names": [...]}
  * `<speakers_json>` — speaker contact details. Schema per item:
        {"ID", "Name", "Email", ...}

One Attendee is emitted per `(speaker, confirmed-session)` pair, so a speaker
who gives N confirmed sessions gets N certs. The matching email comes from the
speakers file (joined on the speaker ID). Sessions that reference a speaker
whose email is missing in the speakers file produce a warning and are skipped.
"""

import json
from pathlib import Path

from participation_certificate import logger
from participation_certificate.models.attendee import Attendee


class ProcessSpeakers:
    """Flatten the confirmed-sessions list into per-(speaker, session) Attendees."""

    def __init__(self, sessions_path: Path, speakers_path: Path):
        self.sessions_path = sessions_path
        self.speakers_path = speakers_path
        self.attendees: list[Attendee] = self._load()

    def _load(self) -> list[Attendee]:
        speakers = json.loads(self.speakers_path.read_text(encoding="utf-8"))
        email_by_id = {
            (s.get("ID") or "").strip(): (s.get("Email") or "").strip()
            for s in speakers
            if s.get("ID")
        }
        logger.info(
            f"Loaded {len(speakers)} speakers from {self.speakers_path} "
            f"({sum(1 for v in email_by_id.values() if v)} with email)."
        )

        sessions = json.loads(self.sessions_path.read_text(encoding="utf-8"))
        logger.info(f"Loaded {len(sessions)} confirmed sessions from {self.sessions_path}")

        attendees: list[Attendee] = []
        for session in sessions:
            proposal_id = (session.get("ID") or "").strip()
            proposal_title = (session.get("Proposal title") or "").strip()
            speaker_ids = session.get("Speaker IDs") or []
            speaker_names = session.get("Speaker names") or []

            if not (proposal_id and proposal_title and speaker_ids):
                logger.warning(f"Skipping incomplete session: {session}")
                continue

            for sid_raw, sname_raw in zip(speaker_ids, speaker_names, strict=False):
                speaker_id = (sid_raw or "").strip()
                speaker_name = (sname_raw or "").strip()
                email = email_by_id.get(speaker_id, "")
                if not (speaker_id and speaker_name and email):
                    logger.warning(
                        f"Session {proposal_id} ({proposal_title[:40]}…): cannot resolve "
                        f"speaker_id={speaker_id!r} name={speaker_name!r} email={email!r}"
                    )
                    continue

                first_name = speaker_name.split()[0]
                try:
                    attendees.append(
                        Attendee(
                            full_name=speaker_name,
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
                        f"Error creating speaker Attendee {speaker_name} ({proposal_id}): {e}"
                    )

        logger.info(f"Produced {len(attendees)} speaker certificate records.")
        return attendees
