# UltraBike Automatizacija

UltraBike Automatizacija is a Windows desktop application for maintaining
product data in Pimbo. It combines an authenticated Selenium browser with
guided upload, batch-editing, review, brand-tool, Orbea, and earnings workflows.

Pimbo is the supported product-management system. Pimbo MagicAI title,
description, category, translation, and specification actions remain supported,
and the title and description template names can be changed in Settings.

## Install and run

For normal use, install the Windows release and launch **UltraBike
Automatizacija**. On first use, create a master password, save the administrator
credentials on Account, and sign in. The app opens and owns the authenticated
Pimbo browser used by automation jobs.

For development:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
```

Python 3.11–3.13 is recommended. Chrome, Firefox, or Edge must be installed for
browser workflows.

## Workflows

- **Upload** prepares one product in Pimbo and records the result.
- **Unified Batch** applies supported title, description, variant, and product
  actions to a reviewed table of products.
- **Descriptions** stores manually maintained LT, EN, and LV templates.
- **Folders and scanners** create output folders and collect specifications,
  names, codes, and brand URLs.
- **Image tools** download and organize supported brand assets.
- **Orbea** matches catalogue and Pimbo records, downloads selected images and
  descriptions, writes a review workbook, and resumes from checkpoints.
- **Analytics, history, and earnings** combine app activity with manually
  recorded work, showing earnings, brands, product types, sources, automation
  reliability, and completed products without double-counting imports. Money
  goals also accept goal-only progress that does not inflate earnings, products,
  Analytics, or hourly rates.
- **Activity** shows queued, running, stopping, completed, partial, failed,
  cancelled, and interrupted jobs. It can cancel supported jobs, reopen their
  workflow/output, and copy diagnostics.

Only one workflow may navigate the shared authenticated Pimbo browser at a time.
See [the Pimbo workflow guide](docs/pimbo-workflow.md) for operating details.

## Local data and security

By default, runtime data is stored in:

```text
%APPDATA%\UltraBike_Automatizacija
```

This includes `ultrabike.db`, `session.dat`, logs, and the default backups
folder. Set `ULTRABIKE_DATA_DIR` to use another base folder. A `portable.flag`
next to the executable keeps runtime data beside the application.

Administrator and supported brand credentials are encrypted with keys derived
from the master password. The auto-login session is additionally bound to the
current Windows user. Changing the master password transactionally re-encrypts
all credentials. Forgotten-password reset preserves non-secret application data
but removes credentials and the auto-login session.

## Backups

Settings → Data safety creates portable `.ubbackup` files. A backup snapshots
SQLite through its backup API, packages application settings, templates,
history, earnings, and encrypted credentials, then encrypts and authenticates
the package with AES-256-GCM using a Scrypt-derived key.

Backups exclude sessions, logs, caches, and external output folders. Restore
validates the password, authenticated format, schema compatibility, and SQLite
integrity before an atomic replacement. A timestamped rollback database remains
beside the live database, and the app restarts after a successful restore.

Keep the backup password separately; neither the app nor the backup stores it.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\smoke_imports_ui.py
.\.venv\Scripts\python.exe main.py --smoke-test
.\.venv\Scripts\python.exe -m pip check
```

The smoke mode requires no login and makes no network requests. It validates
packaged translation resources, route registration, migrations, SQLite, and the
operation tracker.

## Packaging

Build the windowed executable in the active environment:

```powershell
.\build_pyinstaller.ps1
```

For a clean isolated build:

```powershell
.\build_pyinstaller_clean.ps1
```

Both scripts run the packaged offline smoke test. Runtime databases, sessions,
logs, and credentials are deliberately absent from the PyInstaller bundle.

## Releases and updates

The root `latest.json` is the only update manifest. After the Windows installer
has been built, generate the manifest and its installer SHA-256:

```powershell
.\.venv\Scripts\python.exe tools\build_update_manifest.py `
  InstallerOutput\UltraBike_Automatizacija_Setup_2.0.0.exe `
  --version 2.0.0 `
  --url https://example.invalid/releases/UltraBike_Automatizacija_Setup_2.0.0.exe `
  --notes "Release summary"
```

Replace the example URL with the final HTTPS release asset URL. Never hand-copy
another manifest into `InstallerOutput`; the generator always writes the root
manifest. Commit `VERSION.txt`, `CHANGELOG.md`, and the generated `latest.json`
together, then verify the hosted installer hash before publishing.

Update checks can be enabled or disabled in Settings and can be run immediately
with **Check now**. Downloads require HTTPS and a matching SHA-256 digest.
