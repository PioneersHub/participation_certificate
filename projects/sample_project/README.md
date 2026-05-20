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
| `_data/` | Attendee CSV, masterclass XLSX, speaker sessions + speakers JSON. |
| `graphics/` | The three cert-background PDFs (`Attendee Certificate.pdf`, `Masterclass Certificate.pdf`, `Speaker Certificate.pdf`). |
| `branding/logo.png` | Email-header logo (PNG, RGBA, ~880 px wide, < 100 KB). |
| `branding/master.png` | *(optional)* full-resolution source the working copy was resampled from. |

All sub-dirs are gitignored (the project's per-event state is local-only).
`_certificates/` is the output tree — created automatically by the generator.

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
