# sample_project — per-event template

Copy this folder, rename it to your event slug, and fill in `config.yaml` for a
new event:

```bash
cp -r projects/sample_project projects/your-conference
export CERTIFICATE_PROJECT_SLUG=your-conference
$EDITOR projects/your-conference/config.yaml
```

Then create the per-event sub-dirs alongside `config.yaml` and drop the
operator-supplied artefacts into them:

| Sub-dir | What goes here |
| --- | --- |
| `_secret/mailgun_key` | One-line plaintext file with the Mailgun API key. |
| `_signatures/keyStore.p12` | PKCS#12 signing keystore. |
| `_signatures/keystore_password` | One-line plaintext keystore password. |
| `_data/` | Attendee CSV (or the Pretix check-in xlsx it is generated from), masterclass XLSX, speaker sessions + speakers JSON. |
| `graphics/` | The three cert-background PDFs (`Attendee Certificate.pdf`, `Masterclass Certificate.pdf`, `Speaker Certificate.pdf`). |
| `branding/logo.png` | Email-header logo (PNG, RGBA, ~880 px wide, < 100 KB). |
| `branding/master.png` | *(optional)* full-resolution source the working copy was resampled from. |

All sub-dirs are gitignored (the project's per-event state is local-only).
`_certificates/` is the output tree — created automatically by the generator.

## Attendee data from a Pretix check-in list

The attendee CSV (`attendees_table`) can be generated from a Pretix **check-in
list** export rather than hand-written. Download the list as Excel (Pretix →
*Check-in lists → Export → "Check-in list"*), drop it in `_data/`, point
`attendee_checkin.checkin_table` at it, then run:

```bash
uv run python participation_certificate/preprocess_checkin.py
```

It maps `Attendee name: Given/Family name` + `Company` + `Email` to the canonical
`first name / last name / organisation / email` columns and marks every row
`onsite`. See the on-site/remote heuristic and the full column map in
[`docs/walkthrough.md`](../../docs/walkthrough.md) §3.1.

## Signing keystore (`keyStore.p12`)

The generator signs each PDF with a PKCS#12 bundle (private key + certificate
chain) read by [`signing.py`](../../participation_certificate/signing.py) and
loaded via `cryptography`'s `pkcs12.load_key_and_certificates`. Leave
`signing.sign_key` empty in `config.yaml` to skip signing entirely (PDFs are
then encrypted-only).

This project's trust model is **website-based** (each cert carries a UUID +
hash validated against the published site), so the signing certificate only
needs to be cryptographically valid — it does not need Adobe AATL trust.

### From a certbot (Let's Encrypt) certificate

Use this when you already run certbot for a domain you control. Obtain a cert
(skip if you already have a live one):

```bash
sudo certbot certonly --standalone -d certs.example.com
# → /etc/letsencrypt/live/certs.example.com/{privkey,cert,chain,fullchain}.pem
```

Pick a keystore password and store it (one line, **no trailing newline**):

```bash
SLUG=your-conference
DIR="projects/$SLUG/_signatures"
mkdir -p "$DIR"
printf 'choose-a-strong-password' > "$DIR/keystore_password"
```

Bundle the certbot key + leaf cert + chain into the PKCS#12 keystore. Passing
`cert.pem` as the leaf and `chain.pem` via `-certfile` lets the signer embed
the full chain (`othercerts`) in the signature:

```bash
LIVE=/etc/letsencrypt/live/certs.example.com
sudo openssl pkcs12 -export \
  -inkey "$LIVE/privkey.pem" \
  -in    "$LIVE/cert.pem" \
  -certfile "$LIVE/chain.pem" \
  -out "$DIR/keyStore.p12" \
  -passout "file:$DIR/keystore_password"
sudo chown "$USER" "$DIR/keyStore.p12"   # certbot files are root-owned
```

Then point `config.yaml` at it:

```yaml
signing:
  sign_key: "keyStore.p12"
  sign_password_path: "_signatures/keystore_password"
  contact: "certificates@example.com"
  location: "Berlin, Germany"
  reason: "Certificate of participation"
```

Verify the bundle:

```bash
openssl pkcs12 -info -in "$DIR/keyStore.p12" \
  -passin "file:$DIR/keystore_password" -nokeys
```

**Caveats with Let's Encrypt certs:**

- They are domain-validated **TLS server** certs (EKU `serverAuth`) and are
  **not** in Adobe's AATL, so PDF readers show "signature validity unknown"
  rather than a trusted green check. The signature is still real and
  tamper-evident, and validation here happens on the website regardless.
- They expire every **90 days**. The signing date is embedded at generation
  time, so an expired cert does not retroactively invalidate already-signed
  PDFs — but rebuild `keyStore.p12` from the renewed files before each new
  generation run.

> Need an Adobe-trusted green check? Use a document-signing cert from an AATL
> CA (GlobalSign, DigiCert, …); the bundling step (`openssl pkcs12 -export`) is
> identical once you have their key + cert.

## Activate this project

```bash
export CERTIFICATE_PROJECT_SLUG=your-conference     # or: sample_project
```

Every CLI in this repo refuses to run without `CERTIFICATE_PROJECT_SLUG` set
and fails fast with a list of `projects/*` directories it can see.

## Operator runbook

The end-to-end flow (generate → publish validation → preview → smoke → real
send → reissue) is documented in
[`docs/walkthrough.md`](../../docs/walkthrough.md). It is structured for both
human operators and coding agents — Goal → Preconditions → Command → Verify →
Troubleshoot per step.

## Schema reference

- Repo defaults live in [`config.yaml`](../../config.yaml) at the repo root;
  the per-event `config.yaml` here overlays them.
- Required body fields after the `email.body.default` + `email.body.<type>`
  merge: `greeting`, `intro`, `download_intro`, `cta_label`, `post_cta`,
  `closing`, `signature`, `sign_off`. Missing field → clear `RuntimeError`.
- Repo-wide vs. project-relative dir keys are flagged in the schema comments;
  rename a `dirs.path_to_*` value to relocate a sub-dir (e.g. `credentials/`
  instead of `_secret/`).
