# Certificate of Participation

Issue thousands of signed, secure PDF certificates per event and deliver them via branded HTML email. Event-agnostic boilerplate — designed for conference certificates of attendance, training certificates, vouchers, and similar.

| | What it means |
| --- | --- |
| **Signed** | Every PDF is digitally signed with a PKCS#12 keystore and cannot be altered. |
| **Secure** | PDF permissions disallow copying text and modifying the document. |
| **Validated on a website** | A short URL per cert resolves to a public validation page on the event site. |
| **Branded HTML delivery** | Mailgun-sent emails with inline-CID logo, brand colours, PDF attached, plain-text fallback. |
| **Idempotent retry** | Re-running the sender skips already-delivered records and retries the rest. |
| **Single-cert reissue** | A name correction re-cuts one PDF + one validation page while keeping every published URL stable. |

[Full documentation](https://pioneershub.github.io/participation_certificate/) · [Walkthrough (operator runbook)](docs/walkthrough.md)

## Three cert types, three data sources

| Type | Source | What `ticket_reference` derives from |
| --- | --- | --- |
| **Attendee** | CSV under `_data/` (`conf.attendees_table`) | the attendee's email |
| **Masterclass** | XLSX under `_data/` (`conf.masterclass.attendees_table`) | `Order code + Product` (so one order with two half-day masterclasses → two distinct certs) |
| **Speaker** | Two JSON files (`conf.speaker.sessions_json` = confirmed sessions; `conf.speaker.speakers_json` = email directory) | the confirmed session ID; one cert per `(speaker, session)` pair |

UUIDs and hashes are derived deterministically from `full_name + ticket_reference`, so re-runs are safe and reissues with a stable UUID are possible.

## Operational pipeline (five steps)

```bash
# 0. Bootstrap once per machine
uv venv && uv pip install -e ".[dev]"

# 1. Generate signed PDFs per cert type
uv run python participation_certificate/run.py --type attendee
uv run python participation_certificate/run.py --type masterclass
uv run python participation_certificate/run.py --type speaker

# 2. Publish attendee validation pages to the PyCon website checkout
uv run python participation_certificate/validation_upload.py

# 3. Dry-run preview every email locally (writes HTML + xlsx index, sends nothing)
uv run python participation_certificate/deliver_certificates.py --type attendee --dry-run

# 4. Smoke-send a few to a test inbox (records are not mutated)
uv run python participation_certificate/deliver_certificates.py \
    --type attendee --limit 3 --override-recipient you@example.com

# 5. Real send (idempotent; re-running picks up only unsent / failed records)
uv run python participation_certificate/deliver_certificates.py --type attendee
```

For a corrected name on a single cert (preserves UUID + hash + all published URLs):

```bash
uv run python participation_certificate/reissue.py \
    --uuid <uuid> --full-name "Corrected Name"
# Follow the three operator next-steps the tool prints.
```

## Where things live

- **Operator runbook** — [`docs/walkthrough.md`](docs/walkthrough.md) is the canonical step-by-step, structured for both humans and coding agents (Goal → Preconditions → Command → Verify → Troubleshoot per step).
- **Configuration** — `config.yaml` (committed defaults; documented schema) overridden by `config_local.yaml` (gitignored; per-event values). All editable email copy is under `email:` — subjects, layered `body.default` + `body.<type>`, shared legal footer.
- **Brand assets** — [`assets/email/README.md`](assets/email/README.md) explains the master/working-copy split for the email-header logo.
- **Future agents** — root [`CLAUDE.md`](CLAUDE.md) has the architecture brief; per-project skill files (if any) live there too.

## Realization

[Pioneers Hub](https://www.pioneershub.org/en/) helps to build and maintain thriving communities of experts in tech and research to share knowledge, collaborate and innovate together.

![Pioneers Hub Logo](docs/assets/images/Pioneers-Hub-Logo-vereinfacht-inline.svg)
