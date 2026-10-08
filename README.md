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

## Maintenance backlog

Known defects, concurrency risks, and structural debt are tracked in the
[technical debt backlog](docs/technical-debt-backlog.md), with priorities,
evidence, and completion criteria.

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


### Product photos and upload results

Before a product-photo upload, the app checks only the product gallery. It removes the exact Orbea `https://www.orbea.com/uploads/products/images/picture-coming-soon.webp` placeholder, accepts the image-removal confirmation, verifies that it disappeared, and then uploads replacements. Existing real photos cause a successful skip. If real photos and placeholders coexist, only placeholders are removed. A placeholder is kept when there are no replacement photos and no real photos. Geometry and size-table images do not count as product photos.

Use **Export upload results to Excel** in the Orbea or KROSS upload section. The export includes loaded products with saved results and unprocessed products, plus a **Needs checking** sheet. Photo outcomes distinguish uploads, skips, placeholder removals, and whether changes were saved. Saved collection folders retain their latest upload result for export after reopening. For other upload routes, use **Full History → Export to Excel**, which includes the same detailed results and review list alongside the history sheet. Older results retain their original outcome; photo actions that were not recorded are labelled accordingly.


### Orbea colour folders

Collection photo downloads group distinct matched SKUs with the same TTCC model and Orbea link under `products/<TTCC>/<exact SKU>/photos`. For example, `products/U210TTCC` contains `U21005R6`, `U21007R8`, and `U21009R7`. Each SKU receives only the published colour matching its Pimbo product name; Matt/Gloss, punctuation, and spacing do not affect the comparison. For a Custom colour, the app selects **Your Design** and saves its untouched default gallery once per model, then shares those pictures with the Custom SKU folders. It waits for the initial configuration and all full-size default gallery layers to load, combines them into complete views, and keeps Spalva blank. The real **You design** checkbox is supported, including Custom names followed by category text (for example, `/ Custom / kalnų (MTB) dviratis`). A stalled Custom transition gets one fresh-page retry without changing the design. Missing or ambiguous named colours, unavailable design controls, and incomplete default galleries are flagged instead of receiving another colour's pictures.

The model page and selected colours are processed once per link. Common image layers and saved renders remain shared. Additional published colours are not downloaded. The Collected Products Excel sheet records the assigned colour and colour code. Opening an older saved collection and selecting missing photos safely groups its folders, retains source text and upload results, and replaces the uploadable photo list with the assigned colour only. Completed photo sets are skipped on resume; a missing file causes only its colour to be restored. Standalone URL-only photo tools continue to save all published colours because they have no Pimbo SKU/name list.

Earlier unassigned photo sets are retained in a `previous-photos` folder when replaced, so the current `photos` folder contains the matched colour set. Uploads use only the recorded matched files.
