# Walkthrough

End-to-end runbook for issuing conference certificates of attendance: configure → generate → publish validation pages → send branded emails. The pipeline supports three cert types — **attendee**, **masterclass**, **speaker** — each generated independently from its own data source. Validation pages are published only for attendees; the other two types are delivered solely by email.

> **Boilerplate.** The examples below use placeholder names — `your-conference` as the event slug, `Your Conference 2026` as the display name, `your-conference.example.com` for the public website, `certs.example.com` / `your-bucket` for the S3 bucket, `mg.example.com` for the Mailgun domain, `certificates@example.com` for the sender. For a real event, swap these in `config_local.yaml` (gitignored, per-event).

This page is the canonical source of truth. It is structured for both human operators and coding agents: every operational section follows the same shape — **Goal → Preconditions → Command → Verify → Troubleshoot** — and every command is copy-paste runnable.

## 0. At-a-glance reference

### Canonical command sequence (one event, attendee type)

```bash
# one-time bootstrap (repo-wide)
uv venv && uv pip install -e ".[dev]"

# Select the active project. Every CLI below refuses to run without this set.
export CERTIFICATE_PROJECT_SLUG=your-conference     # name of a projects/<slug>/ dir

# generate
uv run python participation_certificate/run.py --type attendee

# distribute the output (MANUAL — see §5.4): upload _certificates/<type>/upload-to-certificates/
# to your PDF host, and copy attendees/website-validate/ into the conference website checkout.
# Do this before sending — the emailed download + "validate online" links point at those hosts.

# preview every email locally — write HTML + xlsx index, send nothing
uv run python participation_certificate/deliver_certificates.py --type attendee --dry-run

# review projects/$CERTIFICATE_PROJECT_SLUG/_certificates/attendees/email-preview/*.html in a browser

# smoke test: real send to a single inbox; records NOT modified
uv run python participation_certificate/deliver_certificates.py \
    --type attendee --limit 3 --override-recipient you@example.com

# real send — idempotent; re-running picks up only unsent/failed records
uv run python participation_certificate/deliver_certificates.py --type attendee
```

For other cert types, swap `--type attendee` for `--type masterclass`, `--type speaker`, `--type volunteer`, etc. The valid `--type` values are derived from config (every enabled block with `load_columns`, plus `speaker` when enabled), so `run.py --type <bad>` prints the configured set.

### File map

Every per-event artefact lives under `projects/${CERTIFICATE_PROJECT_SLUG}/`. The env var `CERTIFICATE_PROJECT_SLUG` (set in the shell before any CLI runs) selects the active project; missing it fails fast with a list of available projects. `TYPE_DIR` is `attendees`, `masterclasses`, or `speakers` (plural on disk). `UUID` and `UTC` are illustrative shell variables an agent can resolve by listing the tree.

| Purpose | Path (relative to repo root) |
| --- | --- |
| Repo-wide config defaults | `config.yaml` |
| Per-event config | `projects/${CERTIFICATE_PROJECT_SLUG}/config.yaml` |
| Source data files | `projects/${CERTIFICATE_PROJECT_SLUG}/_data/` |
| Cert background PDFs | `projects/${CERTIFICATE_PROJECT_SLUG}/graphics/` |
| Signing keystore | `projects/${CERTIFICATE_PROJECT_SLUG}/_signatures/keyStore.p12` |
| Signing password (one-line plaintext) | `projects/${CERTIFICATE_PROJECT_SLUG}/_signatures/keystore_password` |
| Mailgun API key (one-line plaintext) | `projects/${CERTIFICATE_PROJECT_SLUG}/_secret/mailgun_key` |
| Brand logo (CID-inlined into every HTML email) | `projects/${CERTIFICATE_PROJECT_SLUG}/branding/logo.png` |
| Generated PDFs | `projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/${TYPE_DIR}/upload-to-certificates/${UUID}/${UUID}.pdf` |
| Records (source of truth for retry) | `projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/${TYPE_DIR}/records/${UUID}.json` |
| Email previews | `projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/${TYPE_DIR}/email-preview/${UUID}.html` and `${UUID}.txt` |
| Send-attempt index (one per CLI invocation) | `projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/${TYPE_DIR}/email-preview/send-preview-${UTC}.xlsx` |
| Attendee validation Lektor staging | `projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/attendees/website-validate/${UUID}/contents.lr` |
| Shared TTF fonts (repo-wide) | `fonts/` |
| Shared HTML / text layout (repo-wide) | `participation_certificate/email_templates/layout.{html,txt}` |

## 1. Pipeline overview

```text
_data/                    config_local.yaml + config.yaml
   |                              |
   v                              v
run.py --type X  ->  projects/<slug>/_certificates/<type>/{upload-to-certificates, records, website-validate}
                              |
        +---------------------+---------------------------+
        | MANUAL publish (§5.4)                            | (any type)
        v                                                  v
  upload-to-certificates/ -> PDF host (S3 @ certificates_url)   deliver_certificates.py --dry-run
  website-validate/ -> conference website checkout (attendees)     -> email-preview/{*.html,*.txt,*.xlsx}
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
| Active project | `test -n "${CERTIFICATE_PROJECT_SLUG}" && test -d "projects/${CERTIFICATE_PROJECT_SLUG}"` | `export CERTIFICATE_PROJECT_SLUG=<slug>` (or copy `projects/sample_project` for a new event) |
| Project config | `test -f "projects/${CERTIFICATE_PROJECT_SLUG}/config.yaml"` | Lives at `projects/${CERTIFICATE_PROJECT_SLUG}/config.yaml` |
| Signing keystore | `test -f "projects/${CERTIFICATE_PROJECT_SLUG}/_signatures/keyStore.p12"` | Issued by the conference signing authority |
| Signing password file | `test -s "projects/${CERTIFICATE_PROJECT_SLUG}/_signatures/keystore_password"` | Provided alongside the keystore |
| Mailgun API key | `test -s "projects/${CERTIFICATE_PROJECT_SLUG}/_secret/mailgun_key"` | Mailgun dashboard → API keys |
| Brand logo | `test -f "projects/${CERTIFICATE_PROJECT_SLUG}/branding/logo.png"` | See [`docs/branding.md`](branding.md) |
| Attendee cert background | `test -f "projects/${CERTIFICATE_PROJECT_SLUG}/graphics/Attendee Certificate.pdf"` | Designed by the conference team |
| Masterclass cert background (if `masterclass.enabled`) | `test -f "projects/${CERTIFICATE_PROJECT_SLUG}/graphics/Masterclass Certificate.pdf"` | Same |
| Speaker cert background (if `speaker.enabled`) | `test -f "projects/${CERTIFICATE_PROJECT_SLUG}/graphics/Speaker Certificate.pdf"` | Same |
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

#### Generating the CSV from a Pretix check-in list

You normally do **not** hand-write this CSV. Generate it from the ticket
system's check-in list:

1. **Download the check-in list from Pretix.** In the Pretix backend go to
   *Check-in lists → (your list) → Export → "Check-in list"* and pick the
   **Excel (.xlsx)** format. Save it under `_data/` and point
   `attendee_checkin.checkin_table` at the filename (sheet defaults to
   `Check-in list`).
2. **Convert it to the canonical CSV:**

   ```bash
   uv run python participation_certificate/preprocess_checkin.py
   # reads attendee_checkin.checkin_table → writes attendees_table
   ```

The converter ([`preprocess_checkin.py`](../participation_certificate/preprocess_checkin.py))
maps the Pretix columns and carries **every row through** — no filtering on the
`Checked in` column (often empty in exports) and no ticket-type exclusions:

| Pretix column | Canonical CSV column |
| --- | --- |
| `Attendee name: Given name` | `first name` |
| `Attendee name: Family name` | `last name` |
| `Company` | `organisation` |
| `Email` | `email` |
| *(literal `"onsite"`)* | `comment` |

**on site / remote heuristic.** The downstream transformer keys off the
`comment` value: any value containing the substring `"remote"` →
`attended_how = "remotely"`, everything else → `"on site"`. The converter
writes `"onsite"` for every row, so a plain check-in list yields all-on-site
certificates (a physical check-in implies in-person attendance). For a hybrid
event, either edit the generated CSV to set `comment` to something containing
`remote` for online attendees, or merge a separate "online attendees" export
before converting — the converter intentionally does not guess attendance mode.

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

**Downloading from Pretalx.** Both files come from the Pretalx schedule/talk
data, and **only confirmed, accepted sessions must be exported** — the cert is
proof a talk was actually given. In the Pretalx organiser backend filter the
sessions/proposals to **state = "confirmed"** (accepted *and* confirmed for the
schedule; drop "submitted"/"accepted-but-unconfirmed"/"withdrawn"/"rejected")
before exporting, or pull the same set via the API
(`GET /api/events/<event>/submissions/?state=confirmed`, plus
`/api/events/<event>/speakers/`). The exports do not match these field names
verbatim, so a small transform into the schemas below is expected.

**Minimum attributes** the pipeline actually reads
([`preprocess_speakers.py`](../participation_certificate/preprocess_speakers.py)) —
anything else in the export is ignored:

- `sessions_json`: `ID`, `Proposal title`, `Speaker IDs` (list), `Speaker names`
  (list, positionally aligned with `Speaker IDs`). `Session type` is optional.
  A session missing `ID`, `Proposal title`, or `Speaker IDs` is skipped with a
  warning.
- `speakers_json`: `ID`, `Name`, `Email`. A session referencing a Speaker ID
  with no resolvable email in this file is skipped with a warning — never
  silently dropped.

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

### 3.4 Volunteers / Organizers — filtered from the check-in list

Volunteers and organizers get a distinct certificate (cert-type token is
singular: `--type volunteer`; the output dir pluralises to `volunteers/`). Their
input file is carved out of the **same Pretix check-in list** used for attendees:
`preprocess_checkin.py` writes `conf.volunteer.attendees_table` by keeping the
check-in rows whose `Product` contains any substring in
`conf.volunteer.source_products` (case-insensitive), preserving the **raw Pretix
columns** so the masterclass-style `volunteer.load_columns` maps cleanly.

```yaml
volunteer:
  enabled: true
  attendees_table: "your-conference-volunteers.csv"
  source_products: ["organizer", "volunteer"]
  load_columns:
    "Attendee name": "full_name"
    "Attendee name: Given name": "first_name"
    "Email": "email"
    "Order code": "ticket_reference"
    "Product": "masterclass"   # rendered wherever text_items use {attendee.masterclass}
  pdf_background: { file: "Volunteer Certificate.pdf" }
```

Generate the CSV (emitted alongside `attendees.csv` from one read), then verify:

```bash
uv run python participation_certificate/preprocess_checkin.py
uv run python -c "
import pandas as pd
from participation_certificate import conf
v = pd.read_csv('_data/' + conf.volunteer.attendees_table, dtype=str)
assert v['Product'].str.contains('organizer|volunteer', case=False).all()
print('OK', len(v))
"
```

Organizers/volunteers are **also** kept in `attendees.csv`, so they receive both
an attendee and a volunteer certificate.

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

`static_pages_website` is an optional fallback base for the validation link when `validation_url` is unset. Attendee validation pages are generated locally under `_certificates/<event>/attendees/website-validate/<uuid>/contents.lr`; publishing them to a website checkout is a manual step.

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
  ls "projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/attendees/upload-to-certificates" | wc -l   # N PDFs
  ls "projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/attendees/records" | wc -l                  # N record JSONs
  ls "projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/attendees/website-validate" | wc -l         # N validate pages
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
    ls "projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/masterclasses/upload-to-certificates" | wc -l   # N PDFs
  ls "projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/masterclasses/records" | wc -l                   # N records
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
    EXPECTED="$(uv run python -c "
  import json
  from participation_certificate import conf
  print(sum(len(s['Proposal IDs']) for s in json.load(open('_data/' + conf.speaker.speakers_json))))
  ")"
  ACTUAL="$(ls "projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/speakers/records" | wc -l | tr -d ' ')"
  echo "expected ${EXPECTED} certs, produced ${ACTUAL}"
  test "${ACTUAL}" -eq "${EXPECTED}"
  ```

- **Troubleshoot:** as §5.1 plus mismatched count usually means a speaker has unequal-length `Proposal IDs` / `Proposal titles` lists (the loader uses `zip(strict=False)` so the shorter wins).

### 5.4 Distribute the generated artefacts (manual)

Generation only writes to the local `_certificates/` tree. Two **manual** publish
steps make the emailed links resolve, so do them **before** sending (§6+): the
download link points at the hosted PDF, and the "Validate online" link points at
the page on the conference website.

- **Goal:** (1) host every signed PDF behind `certificates_url`; (2) publish the
  attendee validation pages to the conference website.
- **Preconditions:** §5.1–§5.3 done for the types you generated. `aws` is
  configured for the cert bucket; `conf.static_pages_website` is a clean checkout
  of the conference website repo.

- **1. Upload the signed PDFs** — for every cert type you generated, mirror its
  `upload-to-certificates/` tree to the host behind `certificates_url` (public
  pattern `{certificates_url}{uuid}/{uuid}.pdf`). This must include *all* types,
  since the download link in every email points there:

  ```bash
  S3="$(uv run python -c 'from participation_certificate import conf; print(conf.certificates_s3_uri)')"
  for TYPE_DIR in attendees masterclasses speakers volunteers; do
    SRC="projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/${TYPE_DIR}/upload-to-certificates"
    [ -d "${SRC}" ] && aws s3 cp "${SRC}/" "${S3}/" --recursive
  done
  ```

- **2. Publish the attendee validation pages** — copy each
  `attendees/website-validate/<uuid>/contents.lr` into the website checkout under
  `content/attendee-certificate/<uuid>/`, then commit + push **from that checkout**
  (not this repo). Attendee-only — masterclass/speaker/volunteer certs are never
  published to the website:

  ```bash
  WEBSITE="$(uv run python -c 'from participation_certificate import conf; print(conf.static_pages_website)')"
  SRC="projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/attendees/website-validate"
  cp -R "${SRC}/." "${WEBSITE}/content/attendee-certificate/"
  (cd "${WEBSITE}" && git add -f content/attendee-certificate/ \
     && git commit -m "publish attendee validation pages" && git push)
  ```

- **Verify:**

  ```bash
  # PDFs hosted (one per generated cert across all uploaded types):
  aws s3 ls "${S3}/" --recursive | grep -c '\.pdf$'
  # Validation pages now in the website checkout (== attendee count from §5.1):
  find "${WEBSITE}/content/attendee-certificate" -name contents.lr | wc -l
  ```

- **Troubleshoot:**
  - Download link 404s in a delivered email → the PDF was not uploaded, or
    `certificates_url` / `certificates_s3_uri` disagree on bucket + prefix.
  - "Validate online" link 404s → the `contents.lr` was not copied/pushed, or
    `static_pages_website` points at the wrong checkout (the pages must land under
    `content/attendee-certificate/<uuid>/` so the URL `{validation_url}<uuid>/`
    resolves).

## 6. Dry-run email preview

- **Goal:** Render every email locally; produce per-recipient HTML + txt previews and an xlsx index. Nothing is sent.
- **Preconditions:** §5.x done for the target cert type. Mailgun is **not** contacted in dry-run.
- **Command:**

  ```bash
  uv run python participation_certificate/deliver_certificates.py --type attendee --dry-run
  ```

- **Verify:**

  ```bash
    PREVIEW="projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/attendees/email-preview"
  ls "${PREVIEW}"/*.html | wc -l                       # one HTML per job
  ls "${PREVIEW}"/send-preview-*.xlsx | tail -1        # latest xlsx
  # Any leftover ${var} placeholder would indicate a template-renderer bug:
  grep -l '\${' "${PREVIEW}"/*.html | head -1 || echo "OK: no leftover placeholders"
  ```

- **Visual review:** open one `${PREVIEW}/${UUID}.html` in a browser. Check copy, links, brand colours (`#3778be` top rule, `#fac800` CTA), and the absence of `${...}` literals. The CID-inline logo will **not** render in a browser preview (alt text shows instead) — that's expected. §7 confirms the logo renders in a real inbox.
- **Troubleshoot:**
  - `FileNotFoundError: No records dir at ...` — §5.x for this cert type hasn't been run yet (or was wiped). Generate first, then dry-run.
  - `RuntimeError: email.subjects.attendee is not configured` — populate `email.subjects` in `config_local.yaml`.
  - `KeyError` during render — a template references a variable not in the substitution dict; inspect `participation_certificate/email_renderer.py`.

## 7. Smoke test: real send to a test inbox

This step exercises the real Mailgun call with real cert content, but redirects every recipient to one test address. Use it to confirm the logo CID embed renders in real email clients, the PDF arrives intact, and the body links resolve.

- **Goal:** Send N real-content emails to a single test address; verify in the inbox; leave `records/<uuid>.json` untouched so the subsequent real send still picks up every record.
- **Preconditions:** §6 dry-run successful for the target type. `_secret/mailgun_key` and `conf.mailgun.domain` are correct. Operator has access to the test inbox.
- **Command:**

  ```bash
  uv run python participation_certificate/deliver_certificates.py \
      --type attendee \
      --limit 3 \
      --override-recipient you@example.com
  ```

- **Verify (records are not modified):**

  ```bash
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

## 8. Real send

- **Goal:** Deliver every undelivered cert to its real recipient and persist delivery state.
- **Preconditions:** §7 smoke test passed for every cert type you intend to send.
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

## 9. Where logs and rendered messages are persisted

| Artefact | Path | Written by | Lifetime / re-run behaviour |
| --- | --- | --- | --- |
| Per-record state | `projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/${TYPE_DIR}/records/${UUID}.json` — keys `mail_status`, `mail_message_id`, `mail_sent_at`, `mail_failed_at`, `mail_last_error` | `deliver_certificates._persist_status` | Permanent; merged on each successful or failed send; **idempotent retry reads from here** |
| Batch index | `projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/${TYPE_DIR}/email-preview/send-preview-${UTC}.xlsx` — columns `uuid, email, delivered_to, name, subject, status, mail_message_id, preview_html` | `deliver_certificates.write_previews` | One file per CLI invocation; never overwritten |
| Rendered HTML | `projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/${TYPE_DIR}/email-preview/${UUID}.html` | Same | Overwritten on each render |
| Rendered text | `projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/${TYPE_DIR}/email-preview/${UUID}.txt` | Same | Overwritten on each render |
| Signed PDF | `projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/${TYPE_DIR}/upload-to-certificates/${UUID}/${UUID}.pdf` | `Certificates._generate_with_pdf_background` | Permanent until regenerated |
| Validation Lektor page (attendees) | `projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/attendees/website-validate/${UUID}/contents.lr` | `write_validation_page` | Permanent |
| Console log | structlog stdout from each CLI run | structlog default handler | Ephemeral — pipe to a file if you want a transcript |
| Mailgun delivery log | Mailgun dashboard (Sending → Logs) | Mailgun | 3 days (free tier) / 30 days (paid) |

### Invariants for agents

- `records/${UUID}.json` is the **single source of truth** for retry. `mail_status == "sent"` ⇒ skip on re-run; anything else ⇒ retry.
- The xlsx is a snapshot of one CLI invocation; never the source of truth — do not parse it for retry decisions.
- `--override-recipient` runs **never** write to records — smoke tests are non-destructive.

### Quick stats after a send

```bash
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

## 10. Reissue a certificate with a corrected name

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
    projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/<type>/upload-to-certificates/${UUID}/${UUID}.pdf \
    s3://your-bucket/your-conference/${UUID}/${UUID}.pdf

  # 2. (attendee only) Push the new validation page to the PyCon website checkout
  cp projects/${CERTIFICATE_PROJECT_SLUG}/_certificates/attendees/website-validate/${UUID}/contents.lr \
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

## 11. Operational notes

- **Adding a new cert type.** Copy the `masterclass:` block in `config.yaml`, add a loader function in `participation_certificate/run.py`, drop the cert type's body block under `email.body.<type>` in `config_local.yaml`, and add the type to `CERT_TYPES` in `participation_certificate/deliver_certificates.py`.
- **Force a resend of one record.** Prefer `--only ${UUID}` to manually editing the record JSON. Manual edits get out of sync with reality.
- **Mailgun rate limit.** Tune `mailgun.rate_limit_per_sec` in `config_local.yaml` (default `5`). Mailgun's server-side limit on the free tier is higher, but this prevents accidental floods.
- **Adding placeholders to a template.** Add the variable in `email_renderer._build_variables`, then reference `${var_name}` in any body field under `email.body.<type>` in `config_local.yaml`. The renderer raises `KeyError` if a referenced variable is missing — that's the fail-fast guard.
- **CI-friendliness.** Every Verify command in this walkthrough is shell-runnable and exits 0 on success — a coding agent can execute the doc end-to-end as a procedure.
