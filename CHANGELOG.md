# Changelog

This file records shipped UltraBike Automatizacija behavior. Release manifests
are generated from the installer and are not a substitute for this history.

## Unreleased

### Changed

- Product photos, geometry and size tables now share the gallery removal loop
  and confirmation handling. Geometry/size file inputs reset their native value
  without Firefox's Element Clear command, which cannot interact with Pimbo's
  hidden file input. Offline Firefox checks reproduce the original failure and
  verify all 48 attachments across asynchronous input replacements.
- Refreshed table uploads awaiting replacement show New tables need uploading
  instead of the earlier saved status, and are included in unprocessed selection.

- Previously downloaded plain geometry variants are identified in the product
  list and blocked before Pimbo editing. Download missing tables recaptures the
  stale exports; a completed table refresh invalidates the old attachment upload
  stages so Retry unfinished steps also uploads the replacement images.
  Large attachment sets upload in batches of at most twelve files, preserving
  every configuration and verifying cumulative attachments before the next batch.

- Table attachments saved immediately by Pimbo are reloaded and verified even
  when the main Save button is disabled. They report saved_automatically and
  complete the Save step. Older no_changes records containing changed table
  fields remain retryable and are marked for checking in upload reports.

- Pimbo table replacement handles the current Geometry removal confirmation
  before reading the product URL. This prevents Firefox from dismissing the
  pending confirmation through its default unhandled-prompt behaviour. Exact
  gallery-specific confirmations are accepted; unrelated prompts still fail.

- Geometry exports use the same native element screenshot method as Size Tables,
  preserving Orbea's original table and configuration
  fields, without the bike diagram. Captures expand past the dialog's scroll
  limit, keep every row and correct stale displayed selector labels. Capture
  version 6 refreshes previous plain table exports. Size Tables are unchanged.

- Orbea model copying now supports explicit target-paint mappings for the Spalva
  attribute. All 70 supplied paint names have configured values in the copy
  workspace. Gloss/Matt labels distinguish different assignments, including
  Frozen Concrete Gloss → Mėlyna and Matt → Pilka; ambiguous names without finish
  labels preserve the current attribute. Missing mappings preserve existing attributes; missing
  dropdown options block Save. Specification Spalva remains unchanged. Mapping
  changes revisit only relevant saved targets, and results include colour values.

- Orbea Size Tables now replace previous attachments instead of appending
  duplicates. Both table galleries validate replacements, wait for upload, and
  verify the saved URLs after one reload. Selecting either table upload requires
  automatic Save in the service and UI; missing tables or failed uploads block
  Save and remain eligible for retry.

- Orbea table refreshes remove obsolete generated table files only after the new
  set is complete. Uploads use the latest successful table manifest rather than
  all geometry PNGs in the folder, including reports created by earlier running
  versions. Missing current variants and incomplete refreshes block table upload;
  locked leftover files are reported and excluded from the current set.

- Orbea Geometry uploads now validate the full replacement set, remove existing
  geometry attachments, and upload the new configurations without duplicate main
  image aliases. Missing or invalid files preserve existing geometry; upload
  failures block automatic Save. Successful saves reload and verify every
  replacement URL. Product photos and Size Tables stay in their own galleries.

- Orbea geometry downloads now capture all adjustable setting combinations,
  including OCCAM Flipchip × Head Angle, with explicit labels in each PNG.
  Head Angle is no longer mistaken for a frame size; current native selectors
  and refreshed table data are verified despite stale Orbea dropdown widgets.
  Earlier captures are refreshed, and missing configuration files remain retryable.

- Description writes now use HugeRTE's Source Code dialog and its Save control,
  with complete formatted HTML read-back. Attribute selection waits for the
  replacement input after React renders and uses dedicated single-value clear
  buttons when replacing old values.

- Fixed Orbea category copying against Pimbo's current category card: removal
  uses selected chips' × controls, excluding the header MagicAI icon, and exact
  category paths can be selected from its permanent list as well as older popups.

- Orbea model copying now logs each confirmed source-read outcome and a separate
  reading summary, including ready, failed and unread groups. Returning to the
  product list no longer leaves "Reading source" as the last log entry. Stopped
  runs and worker errors are reported without claiming an old checkpoint finished.

- Fixed false empty-description errors during Orbea source reads. The reader
  waits for HugeRTE's iframe and saved LT content, retrying replaced editors
  while preserving the complete description HTML.

- Fixed a false attribute-loading timeout during Orbea source reads. Pimbo's
  empty dropdown buttons and addons are no longer counted as attribute labels;
  hidden companion inputs and open-menu controls are excluded from row detection.
  Unreadable or ambiguous labels now report their actual cause.

- Redesigned Orbea **Model copying** around base TTCC groups: all specific SKUs
  and names are visible with one source selector per group, searchable groups
  and preserved selections. It now uses the app's cards, table theme and run
  sidebar, with stacked controls in narrow windows.

- Orbea report updates continue when the Excel file is open: the app saves an
  updated copy, keeps the original intact, and opens the latest report. Source
  workbook reads and model copying do not require closing Excel.

- Added **Earnings → Add in bulk** for pasted SKUs or Excel SKU/name columns,
  with shared brand, product type and date, a payout preview, duplicate
  handling and an atomic save of the individual earnings records.

- Fixed named-colour photo matching for Pimbo titles that append category and
  wheel size after a separate colour segment, including DENNA M30 Nickel,
  Caramel and Escape Green. The same parsing keeps category text out of Spalva.

- Added an Excel-driven Pimbo photo scan in the Orbea product list. It checks
  selected variant codes for uploaded product-gallery photos, records missing,
  present, not-found and failed checks, and saves the results in the run Excel.
  Missing products can be selected for matched-colour downloads, then uploaded
  and arranged using the photo workflow. Geometry and size tables do not count
  as product photos.

- Simplified Orbea Automation to one **Load products** menu, one additive
  **Selection** menu, **Download selected** with missing/failed, refresh and
  missing-Pimbo-photo modes, and **Upload selected** with an unfinished-step
  retry mode. Product actions use checked, visible rows and retain hidden
  selections. The eligible download count reflects the chosen data stages.
- Downloads now include incomplete checkpoint rows, validate every selected
  collection before starting, and save their scope and stage choices for
  interruption recovery. Resume uses the identified saved run and preserves
  stages completed during the interrupted operation. Refreshing photos makes
  those photos eligible for upload again.
- Combined Orbea's standalone image forms into one URL list, destination,
  image-type selection and progress display. Description extraction and Excel
  sorting remain in Extra tools. Updated English and Lithuanian labels.
- Orbea panels are built directly in their final layout. A shared controller
  owns worker startup, cancellation and cleanup, keeps selection locked until
  queued results finish, and releases browser leases after startup failures.

- Product-photo uploads now replace the entire existing gallery with the
  downloaded photos, rather than skipping products with real images. Removal
  runs once before the upload batches. Missing downloads retain the gallery;
  Orbea results skipped by the old rule remain retryable and are flagged in exports.

- Added an Orbea photo-order step for existing uploads, arranging matched views
  as side, front, back and retaining other gallery images. New uploads with all
  three views are arranged automatically, with the saved order verified in Pimbo.
- Added Orbea product selection by upload status, including failures, No changes
  needed, saved products, and unprocessed products. Status selections add to
  existing checked products; Clear selection explicitly resets them.
- Kept the Orbea upload table scrollable during a run and allowed viewing Activity,
  History, Earnings, Spotify, and Info while the upload retains browser ownership.

- Fixed Pimbo photo uploads when the Images gallery contains both a header
  Upload control and a drop-area control. They now resolve to one gallery,
  allowing Coming Soon placeholder removal while keeping table images separate.
- Product-photo uploads wait for Pimbo to finish media upload and product
  attachment before reporting a confirmed count or navigating to the next bike.
  Attachment errors and partial uploads fail visibly. Photos-only batches no
  longer require form Save; earlier unverified No changes photo results can be
  retried and are flagged in exports.

- Applied the proposed layouts across automation, Earnings, Settings, Account,
  Activity, upload history, sign-in, help, translations, and Spotify, using
  Fluent spacing tokens and native controls. Setup and review sit beside run
  and upload panels, which stack on narrower windows.
- Grouped brand URL and image tools into tabbed workspaces, and added the
  specification checker to Product lookup. Existing tool links select the
  corresponding tab, and running work remains guarded during navigation and
  shutdown.

- Removed retired regular/batch upload choices from the earnings Records source
  filter. Historical earnings remain visible under All sources. Removed unused
  retired upload, batch, analytics, and extended-mode translations in both languages,
  retaining the shared strings used by current lookup and specification tools.

- Retired Single Upload, Unified Batch, Descriptions, Folder Creator, and the old
  Analytics screen, including their navigation, UI helpers, and packaging entries.
  Removed the write-only recent-product cache update and obsolete upload settings.
- Combined names-by-code, code export, and name export into Product lookup and
  export. History now opens the detailed records directly. The app opens
  Earnings after sign-in, while old lookup links open the combined tool.
  Orbea/KROSS bulk workflows, supplier descriptions, translations, earnings,
  and existing stored records remain available.


- Split Orbea's standalone description, photo and table-image workflows into
  separate controllers with shared job ownership, cancellation and control locking.
  Failed description URLs now show partial completion. Service factories construct
  classes correctly, browser-construction errors do not trigger a second call, and
  cleanup/report failures preserve partial results while allowing subsequent runs.

- Fixed Custom Orbea photo failures caused by treating the **You design**
  checkbox as a radio option. Default views now combine the complete loaded
  image layers, wait for the initial configuration, and retry a stalled page
  once. Custom names with trailing category text use the same default gallery;
  completed photo sets remain skipped when downloading missing items.

- Custom Orbea photos select **Your Design** and save its initial full-size
  gallery without changing paint, graphics, varnish, or components. The capture
  is shared across Custom sizes on the same model link, uses the existing SKU
  folders and photo retry results, and leaves the colour specification blank.

- Added **Open saved collection** and **Download selected missing items** for
  finished Orbea Excel reports. New choices use saved product links without a
  Pimbo scan or model search, preserve existing data and upload results, and skip
  complete downloads. Copied reports reconnect to their collection when present;
  standalone reports can supply links for a new download collection.
- Pimbo family/brand reads stay within their own controls and ignore page
  headings such as Product Details. Upload batches check existing unsaved edits
  before processing any bike or overwriting retry progress. Failed-item recovery
  verifies the same product after reload instead of requiring its Save button
  to be disabled; stop messages include the actual recovery error.
- Orbea now fills only model, colour, and sorted frame sizes directly. Component
  text is passed to MagicAI with its original labels; the app no longer maps
  components to assumed Pimbo fields such as a charger field.
- Added **Retry failed and unprocessed uploads** for Orbea. Successful uploads
  remain unselected after reload, and verified saved steps are retained when a
  later specification step fails. Confirmed unpublished tables are skipped;
  stale Pimbo result rows trigger another SKU search. The summary prioritises
  the actual stop reason.

- Added **Retry matched downloads** for Orbea: refresh every matched product's
  saved download choices, including successful and unavailable captures, using
  the existing URLs without rescanning Pimbo. Completed runs can be retried.

- Orbea specifications now come from the complete Standard configuration
  articles instead of configurator choices. Old incomplete captures require
  recollection. Confirmed absence of Features copy skips description steps;
  loading failures remain retryable. Failed preparation retains the freshly
  verified Pimbo target so batch
  recovery can continue after a failed item without discarding another product.

- Orbea uploads keep the full model/year and brand, separate colours from the
  name, remove every finish annotation, and sort letter/numeric variant sizes.
  Wheel size, lacquer finish, and Custom colour remain manual fields through
  specification pre-fill and MagicAI, preserving existing manual values.

- Product preparation now rejects missing, malformed, conflicting, or stale
  supplier specifications. Each run keeps separate source files and downloaded
  images; scraper failures stop preparation before product edits.
- Selected description, attribute, specification, image, and MagicAI failures
  are reported as failed preparation. KROSS/Orbea automatic saving is blocked
  when selected stages cannot complete. Ambiguous Rascal/TREK variants require
  explicit selection; Pinarello framesets exclude complete-bike components.
- Removed standard-upload wheel/groupset guesses from old PIMBO content,
  retained KROSS motor/battery data, and rejected ambiguous Octane derailleur
  splitting. Product identity and version checks protect edits and automatic Save.
- Upload/Batch retain browser ownership during work and unsaved review. Stop
  preserves partial results, batch options retain their values, and manual Save
  confirmation updates the exact preparation history entry.

- Orbea logs and progress identify shared TTCC results without implying another
  regional search for each colour/size. Completed "not found" results are also
  reused for other variants when resuming a saved scan.

- Orbea scanning reads visible variant codes and full titles directly from each
  Pimbo list page in one browser call. It strips additional-variant counts,
  avoids product/Variants page visits, preserves full SKUs for uploads, and
  reuses completed rows across pagination and older partial scans.

- Missing saved optional Orbea catalogues no longer disable fresh scans. Scan
  tooltips explain missing login, invalid catalogue paths, and loading filters.

- Orbea reuses saved photo renders across products and runs and shares identical
  PNG storage while retaining each SKU's upload paths. Table packages share the
  original captures, and uploads include photos in colour subfolders.

- Fixed disabled Orbea Resume after restarting the app: completed scans can
  continue website downloads without a Pimbo connection or the original Excel
  catalogue. Resume restores the saved filters and download choices, targets the
  selected checkpoint directly, and explains why the button is unavailable.

- Orbea collection opens a visible browser with a dedicated session that survives
  retries. Website verification waits up to five minutes for the shop to open,
  then continues automatically with the saved scan. Stop remains available, and
  unresolved checks appear as partial work ready to resume instead of Run failed.

- Orbea discovers all country/language shops from the live location selector,
  searches only model codes ending in TTCC, and takes the first exact code's URL
  directly from the search popup. Variants share each lookup; full SKUs, names,
  catalogue candidates and unrelated product pages are no longer used to find
  links. All URLs are saved before selected downloads begin, with regional
  fallback and resumable checkpoints.
- Made Orbea's main action explicit: **Scan Pimbo and collect Orbea data** starts
  a fresh Pimbo scan. Resume continues saved work through its separate button;
  the first step and progress label now name Pimbo directly.
- Simplified Orbea into one Automation page with three numbered steps: collect
  data, choose products, and update Pimbo. Collected products appear automatically;
  extra filters, reports, logs, and standalone tools expand only when needed.
- Added Orbea's Pimbo workflow using the shared KROSS editing and verified-save
  sequence: selectable photos, tables, Features description and MagicAI, family,
  brand, category, translations, source specification pre-fill and MagicAI.
  Saved packages use one representative SKU, verified again before Draft-only
  edits, with per-product results and honest partial/failure statuses.

- Orbea collection now resolves and saves each product's files before searching
  the next code, updating its Excel after each product. Both description tools
  open the Features dialog and save its introduction and all carousel cards.
  Retrying a run refreshes descriptions saved by the older summary extractor.
- Orbea website security checks preserve the scan and partial Excel, including
  checks that appear after page load.
  Resuming moves the previous run error out of the current attempt's diagnostics.
- Fixed Orbea scans failing with a missing product row when Pimbo was still
  refreshing a shorter page. Failed runs now expose their saved partial Excel
  report and checkpoint in the results screen.
- Added an optional Orbea product-code prefix filter with saved settings and
  compatible checkpoint resuming.
- Added Orbea collection from one representative SKU per product: optional
  catalogue matching, public website lookup, and selectable photos, tables,
  descriptions, and specifications saved in SKU folders with resumable stages.
- Fixed Windows builds accidentally bundling an incompatible ICU library from
  external tools on PATH, which prevented Qt from starting.
- Retired the obsolete external translation integration. Description templates
  remain editable in Lithuanian, English, and Latvian.
- Added strict English and Lithuanian resource catalogs with key and placeholder
  validation.
- Added ordered database migrations, encrypted portable backups, transactional
  master-password changes, and an explicit forgotten-password reset.
- Hardened update download cleanup and user-visible error reporting.
- Combined Earnings and processing history in Analytics so manual work outside
  the app contributes to product, revenue, brand, source, and type statistics
  without double-counting imported upload results.
- Added goal-only progress adjustments that can advance a money goal without
  changing earnings totals, product counts, Analytics, or hourly rates.
- Made manual login, saved auto-login, and browser reconnect checks cancellable
  so a blocked Pimbo authentication check can no longer prevent app shutdown.

## 2.0.0

### Supported workflows

- Pimbo product management through the authenticated Selenium browser.
- Pimbo MagicAI title, description, category, translation, and specification
  automation with configurable template names.
- Unified brand upload, batch editing, product scanners, image utilities, and
  the checkpointed Orbea workflow.
- Earnings, analytics, and detailed processing history.

### Security and reliability

- Scrypt-based credential protection and authenticated local sessions.
- HTTPS-only, SHA-256-verified application updates.
- Structured application logs and recoverable Orbea checkpoints.

Older release notes contained features that were never part of the supported
application and have intentionally been removed.


- Product photo uploads now remove and confirm only the exact Orbea coming-soon placeholder, skip galleries with real photos, and preserve placeholders when replacements are missing. Gallery checks exclude Geometry and Size tables; repeated upload batches remain supported.
- Added Excel upload result exports to Orbea and KROSS, including saved outcomes, unprocessed products, photo actions, warnings, and a separate Needs checking sheet. The existing all-brand history export now includes those detailed result sheets.


- Orbea collection photos now use one model-link download pass for all matching SKUs, request only their verified published colours, and save sibling SKU folders under the TTCC model folder. Uploads use each package's assigned colour list. Unknown and ambiguous named colours are flagged; Custom bikes use the untouched Your Design gallery; failures of one colour leave other successful colours available.
- Saved flat collections retain descriptions, specifications, tables and upload history when regrouped. Interrupted moves can be resumed, and download Excel reports include the assigned photo colour and colour code.
