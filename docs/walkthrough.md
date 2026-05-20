# Walkthrough

End-to-end runbook for issuing conference certificates of attendance: configure → generate → publish validation pages → send branded emails. The pipeline supports three cert types — **attendee**, **masterclass**, **speaker** — each generated independently from its own data source. Validation pages are published only for attendees; the other two types are delivered solely by email.

> **Boilerplate.** The examples below use placeholder names — `your-conference` as the event slug, `Your Conference 2026` as the display name, `your-conference.example.com` for the public website, `certs.example.com` / `your-bucket` for the S3 bucket, `mg.example.com` for the Mailgun domain, `certificates@example.com` for the sender. For a real event, swap these in `config_local.yaml` (gitignored, per-event).

This page is the canonical source of truth. It is structured for both human operators and coding agents: every operational section follows the same shape — **Goal → Preconditions → Command → Verify → Troubleshoot** — and every command is copy-paste runnable.

## 0. At-a-glance reference

### Canonical command sequence (one event, attendee type)

```bash
# one-time bootstrap
uv venv && uv pip install -e ".[dev]"

# generate
uv run python participation_certificate/run.py --type attendee

# publish attendee validation pages (attendees only)
uv run python participation_certificate/validation_upload.py

# preview every email locally — write HTML + xlsx index, send nothing
uv run python participation_certificate/deliver_certificates.py --type attendee --dry-run

# review _certificates/<event>/attendees/email-preview/*.html in a browser

# smoke test: real send to a single inbox; records NOT modified
uv run python participation_certificate/deliver_certificates.py \
    --type attendee --limit 3 --override-recipient you@example.com

# real send — idempotent; re-running picks up only unsent/failed records
uv run python participation_certificate/deliver_certificates.py --type attendee
```

For masterclass and speaker certs, swap `--type attendee` for `--type masterclass` or `--type speaker`. Step "publish attendee validation pages" runs **only once for attendees** — the other two types are not published to the website.

### File map

`EVENT_SHORT_NAME` is the value of `conf.event_short_name` (e.g. `your-conference`). `TYPE_DIR` is `attendees`, `masterclasses`, or `speakers` (plural on disk). `UUID` and `UTC` are illustrative shell variables an agent can resolve by listing the tree.

| Purpose | Path (relative to repo root) |
| --- | --- |
| Event-level config (gitignored) | `config_local.yaml` |
| Project defaults | `config.yaml` |
| Source data files | `_data/` |
| Cert background PDFs | `graphics/` |
| Signing keystore | `_signatures/keyStore.p12` |
| Signing password (one-line plaintext) | `_signatures/keystore_password` |
| Mailgun API key (one-line plaintext) | `_secret/mailgun_key` |
| Brand logo (CID-inlined into every HTML email) | `assets/email/your-conference-logo.png` |
| Generated PDFs | `_certificates/${EVENT_SHORT_NAME}/${TYPE_DIR}/upload-to-certificates/${UUID}/${UUID}.pdf` |
| Records (source of truth for retry) | `_certificates/${EVENT_SHORT_NAME}/${TYPE_DIR}/records/${UUID}.json` |
| Email previews | `_certificates/${EVENT_SHORT_NAME}/${TYPE_DIR}/email-preview/${UUID}.html` and `${UUID}.txt` |
| Send-attempt index (one per CLI invocation) | `_certificates/${EVENT_SHORT_NAME}/${TYPE_DIR}/email-preview/send-preview-${UTC}.xlsx` |
| Attendee validation Lektor staging | `_certificates/${EVENT_SHORT_NAME}/attendees/website-validate/${UUID}/contents.lr` |

## 1. Pipeline overview

```text
_data/                    config_local.yaml + config.yaml
   |                              |
   v                              v
run.py --type X  ->  _certificates/<event>/<type>/{upload-to-certificates, records, website-validate}
                              |
        +---------------------+--------------------------+
        |                                                |
        v (attendees only)                               v (any type)
validation_upload.py ->                  deliver_certificates.py --dry-run
   PyCon website checkout                     -> email-preview/{*.html, *.txt, *.xlsx}
                                                         |
                                            review, then real send
                                                         |
                                                         v
                                       Mailgun (HTML + text + PDF + cid:logo)
                                                         |
                                                         v
                                       records/<uuid>.json (mail_status, mail_message_id, ...)
```

## 2. Prerequisites

Every row's "Verify" command must exit 0 before the rest of the walkthrough can run.

| Need | Verify command | Where to get it |
| --- | --- | --- |
| Python 3.12+ | `python3 --version` | <https://www.python.org/downloads/> |
| `uv` installed | `uv --version` | `pipx install uv` or <https://github.com/astral-sh/uv> |
| Project deps installed | `uv run python -c "import participation_certificate"` | `uv venv && uv pip install -e ".[dev]"` |
| Signing keystore | `test -f _signatures/keyStore.p12` | Issued by the conference signing authority |
| Signing password file | `test -s _signatures/keystore_password` | Provided alongside the keystore |
| Mailgun API key | `test -s _secret/mailgun_key` | Mailgun dashboard → API keys |
| Brand logo | `test -f assets/email/your-conference-logo.png` | See `assets/email/README.md` — copy the Dark Blue variant from the Media Kit |
| Attendee cert background | `test -f "graphics/Attendee Certificate.pdf"` | Designed by the conference team; place in `graphics/` |
| Masterclass cert background (if `masterclass.enabled`) | `test -f "graphics/Masterclass Certificate.pdf"` | Same |
| Speaker cert background (if `speaker.enabled`) | `test -f "graphics/Speaker Certificate.pdf"` | Same |
| Attendee CSV present | `uv run python -c "from participation_certificate import conf; from pathlib import Path; p=Path('_data')/conf.attendees_table; assert p.exists() and p.stat().st_size, p"` | Exported from the ticket system |

Coding agents: run every Verify command before proceeding. Any non-zero exit means the prerequisite is unmet — fix and re-check before moving on.

## 3. Data sources & columns

The pipeline maps each source row to the `Attendee` pydantic model (`participation_certificate/models/attendee.py`). UUIDs derive deterministically from `full_name + ticket_reference`, so the same input always produces the same UUID — re-runs are safe.

### 3.1 Attendee — CSV

Source: `_data/${ATTENDEES_TABLE}` (value from `conf.attendees_table`). Format: CSV.

Required source columns (case-sensitive):

| Source column | Maps to | Notes |
| --- | --- | --- |
| `first name` | `Attendee.first_name` | — |
| `last name` | (derives `full_name`) | Concatenated with `first name` |
| `email` | `Attendee.email` and `Attendee.ticket_reference` | The email also seeds the UUID |
| `comment` | `Attendee.attended_how` | Transformed: contains "remote" → `"remotely"`, else `"on site"` |

The mapping + derivation live in `participation_certificate/run.py`:

```python
load_columns = {
    "first name": "first_name",
    "email": "email",
    "comment": "attended_how",
    "full_name": "full_name",
    "ticket_reference": "ticket_reference",
}

def select_rows(data_frame: pd.DataFrame) -> pd.DataFrame:
    """Derive full_name and ticket_reference; the source CSV has neither."""
    data_frame["full_name"] = (
        data_frame["first_name"].str.strip() + " " + data_frame["last name"].str.strip()
    )
    data_frame["ticket_reference"] = data_frame["email"]
    return data_frame

transformers = {
    "attended_how": lambda x: "remotely" if "remote" in str(x).lower() else "on site"
}
```

Verify the source columns are present:

```bash
ATTENDEES_TABLE="$(uv run python -c 'from participation_certificate import conf; print(conf.attendees_table)')"
head -1 "_data/${ATTENDEES_TABLE}" | tr ',' '\n' | sort
# expect output to include: comment, email, first name, last name
```

### 3.2 Masterclass — XLSX

Source: `_data/${conf.masterclass.attendees_table}`. Format: Excel (`.xlsx`).

Required source columns (from `conf.masterclass.load_columns` in `config_local.yaml`):

| Source column | Maps to | Notes |
| --- | --- | --- |
| `Attendee name` | `Attendee.full_name` | — |
| `Attendee name: Given name` | `Attendee.first_name` | — |
| `Email` | `Attendee.email` | — |
| `Order code` | `Attendee.ticket_reference` | Seeds the UUID |
| `Product` | `Attendee.masterclass` | The masterclass title rendered on the cert |

Verify the source columns are present:

```bash
MASTERCLASS_TABLE="$(uv run python -c 'from participation_certificate import conf; print(conf.masterclass.attendees_table)')"
uv run python -c "
import pandas as pd
from participation_certificate import conf
cols = pd.read_excel('_data/' + conf.masterclass.attendees_table).columns.tolist()
required = set(conf.masterclass.load_columns.keys())
missing = required - set(cols)
print('OK' if not missing else f'MISSING: {missing}')
"
# expect: OK
```

### 3.3 Speaker — two JSON files joined on Speaker ID

Speaker certs require **two** JSON files. The split exists because the
"speakers" export lists every proposal a person ever submitted; only the
"sessions" export tells you which proposals were actually confirmed for the
programme.

| File (under `_data/`) | Role |
| --- | --- |
| `${conf.speaker.sessions_json}` | **Source of truth** for which certs to emit — one entry per confirmed session. |
| `${conf.speaker.speakers_json}` | **Contact directory** — used to resolve each `Speaker ID` to an email. |

**Sessions schema** (`sessions_json`) — each session can have multiple co-presenters; one cert is emitted per `(speaker, session)` pair:

```json
[
  {
    "ID": "session-id-string",
    "Proposal title": "Session title rendered on the cert",
    "Session type": {"en": "Talk"},
    "Speaker IDs": ["spkr-1", "spkr-2"],
    "Speaker names": ["Speaker One", "Speaker Two"]
  }
]
```

**Speakers schema** (`speakers_json`) — only `ID`, `Name`, `Email` are read; any other keys (`Proposal IDs`, `Proposal titles`, …) are ignored:

```json
[
  {"ID": "spkr-1", "Name": "Speaker One", "Email": "one@example.org"}
]
```

Join logic in `participation_certificate/preprocess_speakers.py`: for each confirmed session, look up each Speaker ID in the speakers map; emit an `Attendee` with `ticket_reference = session.ID`, `talk_title = session["Proposal title"]`, `speaker_id = the speaker's ID`. Sessions whose Speaker ID is missing from the speakers map produce a warning and are skipped — never silently dropped.

Verify schema, expected count, and that every confirmed session has a resolvable email:

```bash
uv run python -c "
import collections, json
from participation_certificate import conf
sessions = json.load(open('_data/' + conf.speaker.sessions_json))
speakers = json.load(open('_data/' + conf.speaker.speakers_json))
email_by_id = {s['ID']: (s.get('Email') or '').strip() for s in speakers if s.get('ID')}
certs = sum(len(s.get('Speaker IDs') or []) for s in sessions)
missing = [
    (s['ID'], sid) for s in sessions for sid in (s.get('Speaker IDs') or [])
    if sid not in email_by_id or not email_by_id[sid]
]
distinct = len({sid for s in sessions for sid in (s.get('Speaker IDs') or [])})
print(f'{len(sessions)} confirmed sessions; {certs} certs across {distinct} distinct speakers')
print(f'unresolvable (speaker, session) pairs: {len(missing)}')
types = collections.Counter((s.get('Session type') or {}).get('en') for s in sessions)
print('session types:', dict(types))
"
# expect: unresolvable == 0
```

## 4. Configuration

Configuration is layered: `config.yaml` (committed defaults; never edit per-event) is overridden by `config_local.yaml` (gitignored; per-event overrides). Both files are loaded via OmegaConf at import time.

### 4.1 Event metadata

```yaml
event_short_name: "your-conference"
event_full_name: "Your Conference 2026"
certificates_url: "https://s3.eu-central-1.amazonaws.com/certs.example.com/your-conference/"
validation_url: "https://your-conference.example.com/attendee-certificate/"
static_pages_website: "/path/to/your-website-checkout"
```

`static_pages_website` is the local path to the PyCon website checkout; attendee validation pages are copied here by `validation_upload.py`.

### 4.2 Attendee source + batch size

```yaml
attendees_table: "attendees-your-conference.csv"
batch_size: 0   # 0 means "process all"; set to a small N (e.g. 5) for testing
```

### 4.3 PDF signing

```yaml
signing:
  sign_key: "keyStore.p12"
  sign_password_path: "_signatures/keystore_password"
  contact: "certificates@example.com"
  location: "Digital Certificate"
  reason: "Certificate of Attendance Validation"
```

If `sign_key` is empty, PDFs are encrypted-only (not digitally signed). For a real event run, sign.

### 4.4 Email subjects + Mailgun transport

```yaml
email:
  subjects:
    attendee: "Your Certificate of Attendance — ${event_full_name}"
    masterclass: "Your Masterclass Certificate — ${event_full_name}"
    speaker: "Your Speaker Certificate — ${event_full_name}"
  bcc: ""   # set e.g. "certificates@example.com" for an audit copy on every send

mailgun:
  domain: "mg.example.com"
  region: "eu"                # "eu" or "us"
  from_name: "Your Conference 2026"
  from_email: "certificates@example.com"
  api_key_path: "_secret/mailgun_key"
  rate_limit_per_sec: 5
```

Subject templates support `${event_full_name}`, `${first_name}`, `${full_name}`, `${uuid}`, plus type-specific vars (`${masterclass}` / `${talk_title}`).

### 4.5 Branding

```yaml
branding:
  logo_path: "assets/email/your-conference-logo.png"
```

### 4.6 Optional cert types

```yaml
masterclass:
  enabled: true
  attendees_table: "your-conference-masterclasses.xlsx"
  load_columns:
    "Attendee name": "full_name"
    "Attendee name: Given name": "first_name"
    "Email": "email"
    "Order code": "ticket_reference"
    "Product": "masterclass"
  pdf_background:
    file: "Masterclass Certificate.pdf"
  text_items: [ ... ]   # layout — see existing config_local.yaml

speaker:
  enabled: true
  # Source of truth for confirmed sessions (one cert per (speaker, session) pair).
  sessions_json: "your-conference-sessions.json"
  # Speaker directory — used to resolve Speaker IDs to emails.
  speakers_json: "your-conference-speakers.json"
  pdf_background:
    file: "Speaker Certificate.pdf"
  speaker_url_template: "https://your-conference.example.com/program/speakers/{attendee.speaker_id}/"
  talk_url_template: "https://your-conference.example.com/program/talks/{attendee.proposal_id}/"
  text_items: [ ... ]
```

### 4.7 Email body — defaults + per-type overrides

Body copy lives under `email.body`. The renderer merges `email.body.default` (shared by every cert type) with `email.body.<type>` (the per-type override): keys present in the type-specific block win on collision; any key not overridden falls back to default. This keeps event-wide copy in one place while letting each cert type customise the bits that genuinely differ.

```yaml
email:
  body:
    default:
      greeting: "Dear ${first_name},"
      cta_label: "Download your certificate"
      signature: "All the best,"
      sign_off: "The ${event_full_name} team"
      # Other defaults — `download_intro`, `post_cta`, `closing` — typically
      # set here too; per-type blocks override them as needed.

    attendee:
      intro: |
        Your **Certificate of Attendance** for ${event_full_name} is attached.
      post_cta: |
        To verify authenticity, anyone can confirm your certificate at
        [${validation_url}](${validation_url}).

    masterclass:
      intro: |
        Your **Masterclass Certificate** for *${masterclass}* at
        ${event_full_name} is attached.

    speaker:
      intro: |
        Thank you for speaking at ${event_full_name}: ${talk_title}.
  footer: |
    This email was sent to you because you attended ${event_full_name}.
    ${event_full_name} is brought to you by Your Organisation.
    …
```

**Required fields** (after merging default + per-type, every cert type must
have these or the renderer raises a clear `RuntimeError`):
`greeting`, `intro`, `download_intro`, `cta_label`, `post_cta`, `closing`,
`signature`, `sign_off`. Empty string is a legitimate value — it just renders
nothing in that slot.

**Markdown supported in body fields**: `**bold**`, `*italic*`, `[label](url)`.
Converted to HTML in the HTML body, stripped to clean prose in the plain-text
body (so `[Validate](https://…)` becomes `Validate (https://…)` in plain text).

Verify the merged config:

```bash
uv run python -c "
from participation_certificate import conf
print('event:', conf.event_short_name, '|', conf.event_full_name)
print('mailgun:', conf.mailgun.domain, conf.mailgun.from_email)
print('subjects:', dict(conf.email.subjects))
if not (conf.mailgun.domain and conf.mailgun.from_email and conf.email.subjects.attendee):
    raise SystemExit('missing required keys')
"
# expect: three lines + clean exit
```

## 5. Generate certificates

Run one cert type at a time. The generator is idempotent at the path level — re-running produces the same UUIDs and overwrites the same files.

### 5.1 Generate attendee certificates

- **Goal:** Render and sign every attendee PDF; write the validation Lektor page for each.
- **Preconditions:** §2 + §3.1 verifications pass.
- **Command:**

  ```bash
  uv run python participation_certificate/run.py --type attendee
  ```

- **Verify:**

  ```bash
  EVENT="$(uv run python -c 'from participation_certificate import conf; print(conf.event_short_name)')"
  ls "_certificates/${EVENT}/attendees/upload-to-certificates" | wc -l   # N PDFs
  ls "_certificates/${EVENT}/attendees/records" | wc -l                  # N record JSONs
  ls "_certificates/${EVENT}/attendees/website-validate" | wc -l         # N validate pages
  # All three counts must match the row count of the attendee CSV (modulo batch_size).
  ```

- **Troubleshoot:**
  - `FileNotFoundError: graphics/Attendee Certificate.pdf` — drop the background PDF in `graphics/`.
  - `NO sign_key -> NOT signing` log line — set `signing.sign_key` and ensure `_signatures/keyStore.p12` + `_signatures/keystore_password` exist.
  - Only 2 records processed — `batch_size` in `config_local.yaml` is `2`; set to `0` to process all.

### 5.2 Generate masterclass certificates

- **Goal:** Render every masterclass PDF.
- **Preconditions:** §2 + §3.2 verifications pass. `conf.masterclass.enabled` is `true`.
- **Command:**

  ```bash
  uv run python participation_certificate/run.py --type masterclass
  ```

- **Verify:**

  ```bash
  EVENT="$(uv run python -c 'from participation_certificate import conf; print(conf.event_short_name)')"
  ls "_certificates/${EVENT}/masterclasses/upload-to-certificates" | wc -l   # N PDFs
  ls "_certificates/${EVENT}/masterclasses/records" | wc -l                   # N records
  # No new website-validate entries are produced for masterclass certs — that
  # tree only exists for attendees by design. A pre-existing
  # masterclasses/website-validate/ directory from before this design rule was
  # introduced is harmless and can be safely deleted.
  ```

- **Troubleshoot:** as §5.1 plus `masterclass.enabled is false — nothing to do.` — enable the type in `config_local.yaml`.

### 5.3 Generate speaker certificates

- **Goal:** Render every speaker PDF (one per `(speaker, proposal)` pair).
- **Preconditions:** §2 + §3.3 verifications pass. `conf.speaker.enabled` is `true`.
- **Command:**

  ```bash
  uv run python participation_certificate/run.py --type speaker
  ```

- **Verify:**

  ```bash
  EVENT="$(uv run python -c 'from participation_certificate import conf; print(conf.event_short_name)')"
  EXPECTED="$(uv run python -c "
  import json
  from participation_certificate import conf
  print(sum(len(s['Proposal IDs']) for s in json.load(open('_data/' + conf.speaker.speakers_json))))
  ")"
  ACTUAL="$(ls "_certificates/${EVENT}/speakers/records" | wc -l | tr -d ' ')"
  echo "expected ${EXPECTED} certs, produced ${ACTUAL}"
  test "${ACTUAL}" -eq "${EXPECTED}"
  ```

- **Troubleshoot:** as §5.1 plus mismatched count usually means a speaker has unequal-length `Proposal IDs` / `Proposal titles` lists (the loader uses `zip(strict=False)` so the shorter wins).

## 6. Publish attendee validation pages

- **Goal:** Make `https://your-conference.example.com/attendee-certificate/${UUID}/` resolve for every attendee. Only attendees are published; masterclass and speaker certs are not on the website.
- **Preconditions:** §5.1 done. `conf.static_pages_website` points at a clone of the conference website repo with a clean `git status`.
- **Command:**

  ```bash
  uv run python participation_certificate/validation_upload.py
  ```

- **Verify:**

  ```bash
  WEBSITE="$(uv run python -c 'from participation_certificate import conf; print(conf.static_pages_website)')"
  find "${WEBSITE}/content/attendee-certificate" -name contents.lr | wc -l
  # expect: equal to the attendee count from §5.1 Verify
  ```

- **Then commit and push from the website checkout (not this repo):**

  ```bash
  WEBSITE="$(uv run python -c 'from participation_certificate import conf; print(conf.static_pages_website)')"
  cd "${WEBSITE}"
  git add -f content/attendee-certificate/
  git commit -m "publish attendee validation pages"
  git push
  ```

- **Troubleshoot:** zero results from the `find` means the script ran against an empty `records/` directory — re-run §5.1 first. Masterclass / speaker certs are never synced; that is correct behaviour.

## 7. Dry-run email preview

- **Goal:** Render every email locally; produce per-recipient HTML + txt previews and an xlsx index. Nothing is sent.
- **Preconditions:** §5.x done for the target cert type. Mailgun is **not** contacted in dry-run.
- **Command:**

  ```bash
  uv run python participation_certificate/deliver_certificates.py --type attendee --dry-run
  ```

- **Verify:**

  ```bash
  EVENT="$(uv run python -c 'from participation_certificate import conf; print(conf.event_short_name)')"
  PREVIEW="_certificates/${EVENT}/attendees/email-preview"
  ls "${PREVIEW}"/*.html | wc -l                       # one HTML per job
  ls "${PREVIEW}"/send-preview-*.xlsx | tail -1        # latest xlsx
  # Any leftover ${var} placeholder would indicate a template-renderer bug:
  grep -l '\${' "${PREVIEW}"/*.html | head -1 || echo "OK: no leftover placeholders"
  ```

- **Visual review:** open one `${PREVIEW}/${UUID}.html` in a browser. Check copy, links, brand colours (`#3778be` top rule, `#fac800` CTA), and the absence of `${...}` literals. The CID-inline logo will **not** render in a browser preview (alt text shows instead) — that's expected. §8 confirms the logo renders in a real inbox.
- **Troubleshoot:**
  - `FileNotFoundError: No records dir at ...` — §5.x for this cert type hasn't been run yet (or was wiped). Generate first, then dry-run.
  - `RuntimeError: email.subjects.attendee is not configured` — populate `email.subjects` in `config_local.yaml`.
  - `KeyError` during render — a template references a variable not in the substitution dict; inspect `participation_certificate/email_renderer.py`.

## 8. Smoke test: real send to a test inbox

This step exercises the real Mailgun call with real cert content, but redirects every recipient to one test address. Use it to confirm the logo CID embed renders in real email clients, the PDF arrives intact, and the body links resolve.

- **Goal:** Send N real-content emails to a single test address; verify in the inbox; leave `records/<uuid>.json` untouched so the subsequent real send still picks up every record.
- **Preconditions:** §7 dry-run successful for the target type. `_secret/mailgun_key` and `conf.mailgun.domain` are correct. Operator has access to the test inbox.
- **Command:**

  ```bash
  uv run python participation_certificate/deliver_certificates.py \
      --type attendee \
      --limit 3 \
      --override-recipient you@example.com
  ```

- **Verify (records are not modified):**

  ```bash
  EVENT="$(uv run python -c 'from participation_certificate import conf; print(conf.event_short_name)')"
  # All mail_status fields must remain null after a smoke send.
  uv run python -c "
  import glob, json
  from participation_certificate import conf
  paths = glob.glob(f'_certificates/{conf.event_short_name}/attendees/records/*.json')
  statuses = {json.load(open(p)).get('mail_status') for p in paths}
  print('mail_status values:', statuses)
  assert statuses <= {None}, 'smoke send unexpectedly persisted mail_status'
  "
  # expect: mail_status values: {None}  (no AssertionError)
  ```

- **Verify (inbox):** for each of the N messages received, check:
  - Branded header with the actual conference logo rendered (proves the CID inline embed worked).
  - Subject line matches `conf.email.subjects.attendee` after substitution.
  - Body copy contains the real first name, event name, download URL and validation URL (attendees only).
  - PDF attached; opening it shows the signed certificate with the real attendee's name.
  - Download URL clicks through to the PDF on the certificates S3 bucket.
- Repeat with `--type masterclass` and `--type speaker` to smoke each template.
- **Troubleshoot:**
  - Mailgun HTTP `401 Unauthorized` — wrong key in `_secret/mailgun_key` or wrong `mailgun.domain`.
  - Mailgun HTTP `404` — `mailgun.domain` is not provisioned on the Mailgun account.
  - Logo missing in the inbox — `assets/email/your-conference-logo.png` missing or wrong filename; re-check §2.
  - No messages received — confirm the inbox isn't a Mailgun-blocked test domain (use a real address).

## 9. Real send

- **Goal:** Deliver every undelivered cert to its real recipient and persist delivery state.
- **Preconditions:** §8 smoke test passed for every cert type you intend to send.
- **Command:**

  ```bash
  uv run python participation_certificate/deliver_certificates.py --type attendee
  # repeat with --type masterclass and --type speaker as needed
  # optional flags:
  #   --bcc certificates@example.com   audit copy of every send
  #   --limit 50                    roll out in waves
  #   --only 4600e5d3-...           resend a specific uuid
  ```

- **Verify:**

  ```bash
  EVENT="$(uv run python -c 'from participation_certificate import conf; print(conf.event_short_name)')"
  uv run python -c "
  import collections, glob, json
  from participation_certificate import conf
  paths = glob.glob(f'_certificates/{conf.event_short_name}/attendees/records/*.json')
  counts = collections.Counter(json.load(open(p)).get('mail_status') for p in paths)
  print(dict(counts))
  "
  # expect: {'sent': N}  (or a mix of sent + failed; no records left as None after a full run)
  ```

- **Idempotent retry:** records with `mail_status == "sent"` are skipped on re-run; records with `mail_status == "failed"` (or unset) are retried. Re-run the same command to retry only the stragglers.
- **Troubleshoot:**
  - `MailgunSendError: HTTP 429` — rate limited; lower `conf.mailgun.rate_limit_per_sec`.
  - Persistent same-error failures — inspect the record JSON's `mail_last_error`; common causes are invalid email (pydantic validation) or a missing PDF.
  - Sent but not received — check the Mailgun dashboard at <https://app.eu.mailgun.com/> for delivery status, bounces, spam complaints.

## 10. Where logs and rendered messages are persisted

| Artefact | Path | Written by | Lifetime / re-run behaviour |
| --- | --- | --- | --- |
| Per-record state | `_certificates/${EVENT}/${TYPE_DIR}/records/${UUID}.json` — keys `mail_status`, `mail_message_id`, `mail_sent_at`, `mail_failed_at`, `mail_last_error` | `deliver_certificates._persist_status` | Permanent; merged on each successful or failed send; **idempotent retry reads from here** |
| Batch index | `_certificates/${EVENT}/${TYPE_DIR}/email-preview/send-preview-${UTC}.xlsx` — columns `uuid, email, delivered_to, name, subject, status, mail_message_id, preview_html` | `deliver_certificates.write_previews` | One file per CLI invocation; never overwritten |
| Rendered HTML | `_certificates/${EVENT}/${TYPE_DIR}/email-preview/${UUID}.html` | Same | Overwritten on each render |
| Rendered text | `_certificates/${EVENT}/${TYPE_DIR}/email-preview/${UUID}.txt` | Same | Overwritten on each render |
| Signed PDF | `_certificates/${EVENT}/${TYPE_DIR}/upload-to-certificates/${UUID}/${UUID}.pdf` | `Certificates._generate_with_pdf_background` | Permanent until regenerated |
| Validation Lektor page (attendees) | `_certificates/${EVENT}/attendees/website-validate/${UUID}/contents.lr` + PyCon website checkout | `write_validation_page` + `validation_upload.sync_attendee_validation` | Permanent |
| Console log | structlog stdout from each CLI run | structlog default handler | Ephemeral — pipe to a file if you want a transcript |
| Mailgun delivery log | Mailgun dashboard (Sending → Logs) | Mailgun | 3 days (free tier) / 30 days (paid) |

### Invariants for agents

- `records/${UUID}.json` is the **single source of truth** for retry. `mail_status == "sent"` ⇒ skip on re-run; anything else ⇒ retry.
- The xlsx is a snapshot of one CLI invocation; never the source of truth — do not parse it for retry decisions.
- `--override-recipient` runs **never** write to records — smoke tests are non-destructive.

### Quick stats after a send

```bash
EVENT="$(uv run python -c 'from participation_certificate import conf; print(conf.event_short_name)')"
uv run python -c "
import collections, glob, json
from participation_certificate import conf
for ct in ('attendees', 'masterclasses', 'speakers'):
    paths = glob.glob(f'_certificates/{conf.event_short_name}/{ct}/records/*.json')
    if not paths:
        continue
    c = collections.Counter(json.load(open(p)).get('mail_status') for p in paths)
    print(f'{ct:14} total={len(paths):5}  {dict(c)}')
"
```

## 11. Reissue a certificate with a corrected name

When a recipient asks for a name correction (typo, married name, nickname that crept in from the ticket data), `reissue.py` re-cuts a single signed PDF — and only that one — while keeping every published identifier stable.

- **Goal:** regenerate one cert's PDF + validation Lektor page locally with a corrected name. UUID, hash, S3 download URL, and `/attendee-certificate/${UUID}/` validation URL all stay the same so the recipient's existing email link keeps working.
- **Preconditions:** §2 verifications pass; you have the cert's UUID; an active correction request from the recipient.
- **Command:**

  ```bash
  uv run python participation_certificate/reissue.py \
      --uuid <uuid> \
      --full-name "Corrected Name" \
      [--first-name "Corrected"]   # default: first whitespace-split word of --full-name
      [--type attendee]            # attendee | masterclass | speaker
      [--dry-run]                  # preview the diff, write nothing
  ```

- **What it changes locally** (atomic; same on-disk paths as the original):
  - the signed PDF (re-signed under the original UUID)
  - the record JSON (`mail_status` cleared so a follow-up `deliver --only` resends; `mail_message_id` + `mail_sent_at` of the *previous* send preserved as audit history)
  - the validation Lektor `contents.lr` (attendee type only — masterclass/speaker never publish a validation page)
- **What it does not change**: the UUID, the hash, the cert's "No. `<hash>`" serial number, anything outside the corrected name's row.
- **Operator next steps** (the CLI prints these with paths + UUID filled in):

  ```bash
  UUID=<the uuid you reissued>

  # 1. Replace the PDF on S3 (same key — overwrites)
  aws s3 cp \
    _certificates/${EVENT}/<type>/upload-to-certificates/${UUID}/${UUID}.pdf \
    s3://your-bucket/your-conference/${UUID}/${UUID}.pdf

  # 2. (attendee only) Push the new validation page to the PyCon website checkout
  cp _certificates/${EVENT}/attendees/website-validate/${UUID}/contents.lr \
    <WEBSITE>/content/attendee-certificate/${UUID}/contents.lr
  (cd <WEBSITE> && git add -f content/attendee-certificate/${UUID}/contents.lr \
    && git commit -m "reissue ${UUID}" && git push)

  # 3. Resend the email
  uv run python participation_certificate/deliver_certificates.py --type <type> --only ${UUID}
  ```

- **Troubleshoot:**
  - `No record at …` — the UUID is wrong, or the cert hasn't been generated for that event yet.
  - `Record file uuid <x> does not match path uuid <y>` — the record's filename and its `uuid` field disagree (shouldn't happen unless something is hand-edited); refuses rather than guess.
  - `RuntimeError: uuid drifted / hash drifted / full_name not updated` — internal self-check failed; do not publish the result. File a bug.

## 12. Operational notes

- **Adding a new cert type.** Copy the `masterclass:` block in `config.yaml`, add a loader function in `participation_certificate/run.py`, drop the cert type's body block under `email.body.<type>` in `config_local.yaml`, and add the type to `CERT_TYPES` in `participation_certificate/deliver_certificates.py`.
- **Force a resend of one record.** Prefer `--only ${UUID}` to manually editing the record JSON. Manual edits get out of sync with reality.
- **Mailgun rate limit.** Tune `mailgun.rate_limit_per_sec` in `config_local.yaml` (default `5`). Mailgun's server-side limit on the free tier is higher, but this prevents accidental floods.
- **Adding placeholders to a template.** Add the variable in `email_renderer._build_variables`, then reference `${var_name}` in any body field under `email.body.<type>` in `config_local.yaml`. The renderer raises `KeyError` if a referenced variable is missing — that's the fail-fast guard.
- **CI-friendliness.** Every Verify command in this walkthrough is shell-runnable and exits 0 on success — a coding agent can execute the doc end-to-end as a procedure.
