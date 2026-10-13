# UltraBike Automatizacija

UltraBike Automatizacija is a Windows desktop application for maintaining
product data in Pimbo. It combines an authenticated Selenium browser with
dedicated Orbea and KROSS bulk workflows, product lookup, image tools, and earnings.

Pimbo is the supported product-management system. Pimbo MagicAI title,
description, category, translation, and specification actions remain supported,
and the title and description template names can be changed in Settings.

## Install and run

For normal use, install the Windows release and launch **UltraBike
Automatizacija**. On first use, create a master password, save the administrator
credentials on Account, and sign in. The app opens on Earnings and owns the
authenticated Pimbo browser used by automation jobs.

For development:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
```

Python 3.11–3.13 is recommended. Chrome, Firefox, or Edge must be installed for
browser workflows.

## Workflows

- **Orbea** matches catalogue and Pimbo records, collects source data and images,
  writes review workbooks, and uploads selected products with saved retry progress.
- **KROSS** collects supplier products and uploads selected data to Pimbo.
- **Product lookup and export** finds names by code, exports product codes, and
  exports product names from one screen.
- **Translations and specification checking** maintain the dictionary used by
  supplier tools and inspect product specifications.
- **Image and URL tools** collect supported brand assets and product links.
- **History and earnings** retain saved product results, Excel export, manually
  recorded work, earnings, goals, and automation reliability. Goal-only progress
  does not inflate earnings, products, or hourly rates.
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

## Adding earnings in bulk

Earnings → Add in bulk accepts one SKU per line or two copied Excel columns
(SKU and optional product name). Choose the shared brand, product type and
date, review the count and payout, then add all entries together. Existing
and repeated SKUs are skipped unless you explicitly include duplicates as
separate paid work. Each product keeps its own earnings record at the current
rate; a failed batch rolls back all its new entries.

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

Before a product-photo upload, the app verifies the target product and replaces its product gallery with the downloaded photos. The gallery is cleared once before the first batch, including Coming Soon placeholders; later batches retain the new uploads. Missing usable downloads leave the gallery unchanged. The app waits for product attachment to finish and verifies the gallery count. Geometry and size-table images are separate from product photos.

Use **Export upload results to Excel** in the Orbea or KROSS upload section. The export includes loaded products with saved results and unprocessed products, plus a **Needs checking** sheet. Photo outcomes distinguish uploads, skips, placeholder removals, and whether changes were saved. Saved collection folders retain their latest upload result for export after reopening. For historical results, use **History → Export to Excel**, which includes the same detailed results and review list alongside the history sheet. Older results retain their original outcome; photo actions that were not recorded are labelled accordingly.


### Orbea Automation

Use **Load products** for Excel, saved folders, or reloading the current source. **Selection** offers Select visible, Clear visible and additive status selection. Download selected provides missing/failed, refresh, and missing-Pimbo-photo modes with an eligible count. Upload selected offers normal or unfinished-step retry. Product actions process checked, visible rows and preserve hidden checks. Scan Pimbo, Scan Pimbo photos and Resume interrupted run remain distinct; resume restores the identified saved scope. Extra tools combines image URLs, destination and image types in one form, alongside description extraction and Excel sorting.

**Model copying** accepts your regular `orbea_matches.xlsx`. Each base TTCC code appears beside all of its specific SKUs and bike names. Select the source beside the bike already prepared and saved in Pimbo, then check the groups to process. Search by base code, SKU or name; actions use the checked groups currently shown and keep hidden selections. **Read sources** captures the saved data, and **Copy and save** applies it to the remaining bikes. Source choices are remembered separately from Excel; optional `Šaltinis` / `TAIP` marks are still supported. Run controls and the activity log use the same cards and sidebar as the other workflows, stacking below the list in narrow windows.

### Orbea colour folders

Collection photo downloads group distinct matched SKUs with the same TTCC model and Orbea link under `products/<TTCC>/<exact SKU>/photos`. For example, `products/U210TTCC` contains `U21005R6`, `U21007R8`, and `U21009R7`. Each SKU receives only the published colour matching its Pimbo product name; Matt/Gloss, punctuation, and spacing do not affect the comparison. For a Custom colour, the app selects **Your Design** and saves its untouched default gallery once per model, then shares those pictures with the Custom SKU folders. It waits for the initial configuration and all full-size default gallery layers to load, combines them into complete views, and keeps Spalva blank. The real **You design** checkbox is supported, including Custom names followed by category text (for example, `/ Custom / kalnų (MTB) dviratis`). A stalled Custom transition gets one fresh-page retry without changing the design. Missing or ambiguous named colours, unavailable design controls, and incomplete default galleries are flagged instead of receiving another colour's pictures.

The model page and selected colours are processed once per link. Common image layers and saved renders remain shared. Additional published colours are not downloaded. The Collected Products Excel sheet records the assigned colour and colour code. Opening an older saved collection and selecting missing photos safely groups its folders, retains source text and upload results, and replaces the uploadable photo list with the assigned colour only. Completed photo sets are skipped on resume; a missing file causes only its colour to be restored. Standalone URL-only photo tools continue to save all published colours because they have no Pimbo SKU/name list.

Earlier unassigned photo sets are retained in a `previous-photos` folder when replaced, so the current `photos` folder contains the matched colour set. Uploads use only the recorded matched files.
