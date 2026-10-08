# Changelog

This file records shipped UltraBike Automatizacija behavior. Release manifests
are generated from the installer and are not a substitute for this history.

## Unreleased

### Changed

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
