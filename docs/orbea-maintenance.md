# Maintaining the Orbea workflow

The Automation page builds its source, filter, selection, action and progress
panels directly in their final layout. Do not add a build-and-reparent pass:
locking belongs to the workflow controller, including controls in other columns.
Existing service entry points, saved checkpoints and output formats remain
supported; the photo-only selected-download entry point is an adapter.

Pimbo's Base UI attribute combobox replaces its input after an option is chosen.
Resolve the replacement before leaving the field and use Tab, not Escape:
Escape on the closed combobox clears the committed selection. Keep the exact
existing-option and stable read-back checks. Source Spalva is excluded by the
copy service; explicitly mapped target colours use the same dropdown setter.
The Spalva specification must remain unchanged.

Source clicks reuse the loaded snapshot only while workbook and checkpoint
mtime/size stamps match. Write a cloned group atomically before replacing UI
state; reload on external changes and revalidate scope in the existing worker
before editing Pimbo. Group updates retain radio buttons, captions and table
items when row topology is unchanged. Resize only affected groups, refresh
translated text explicitly, and rebuild only when group/SKU rows change.

Copy workers publish each confirmed item together with its immutable snapshot
on progress_ready. The GUI must not reread Excel/checkpoint files in completion
slots. Parallel workers snapshot their shared checkpoint under the existing
lock and serialize publication; browser field work remains concurrent.

## User workflow

- **Scan missing data** checks selected visible products against their full SKU.
  Only required (*) attributes count; empty Ratų dydis and Spalva attributes
  are allowed. Every displayed field in the LT **Bendra informacija** group
  counts, including its colour and wheel-size specifications. Other spec groups
  are ignored. Exact missing names appear in the Pimbo data tooltip, activity
  log and **Pimbo Content** Excel sheet. Select/unselect by status offers missing
  data, attributes, general specs, complete, unchecked, scan errors and not found.
  The scan reads Pimbo without Save or MagicAI. It waits for field hydration and
  stable values, checks product identity/version, and treats loading/schema
  problems as scan errors. Unsaved manual changes block scanning; unsafe
  navigation stops the queue. Stop retains finished checks and other selections.

- Model copying lists only TTCC groups containing multiple distinct bikes.
  The first bike in Excel row order is the default source; a TAIP mark or a
  saved app source choice takes priority, including an explicitly cleared
  choice. Standalone groups stay in the checkpoint but do not appear in the
  list, selection counts or source-read queue.

- **Load products** opens an Excel, a saved folder, or reloads the displayed source.
  Scan results load automatically. The source path stays visible below the filters.
- **Add product** accepts a Pimbo SKU, its model code with TTCC (suggested from the
  SKU; the four-character base is also accepted), name including colour and a
  public Orbea product URL. It appends to the loaded collection or creates a
  local collection without Excel or a Pimbo login. An existing unique SKU updates
  its row; **Edit product** corrects the highlighted row while keeping its SKU,
  checkpoint identity and known Pimbo ID. Products use the usual checked-row
  downloads, scans, uploads and Excel export. Manual links skip supplier search;
  downloaded page codes and photo colours still undergo normal validation.
  Changing a name/link makes old stages pending and clears completed upload
  stages while preserving source files/history. With multiple runs loaded,
  duplicate SKUs require selecting a specific row; new products get a new run
  inside the displayed source. Other row selections are retained.
- **Add product → Import Excel** appends `.xlsx` / `.xlsm` rows in the layout
  A = Pimbo SKU, B = product name, C = TTCC model code, D ignored, E = Orbea URL.
  Headers are optional; recognized headers can also change the column order.
  The Matches sheet is used when present, otherwise the workbook's active sheet.
  Excel hyperlinks are accepted. Blank rows are ignored; identical SKU rows are
  deduplicated, conflicting SKU rows and other invalid rows are reported with
  sheet/row locations. Valid rows import together into one new run or update
  their existing owners. Ambiguous saved SKUs remain unchanged. Import retains
  the current list and other checks, selects imported rows and exports once per
  participating run. The input workbook is preserved, including when importing
  a collection's own report (the refreshed report then uses a separate copy).
- **Selection** offers Select visible and Clear visible. Separate **Select by
  status** and **Unselect by status** menus handle upload and photo scan statuses,
  including Failed, Saved and No photos. Model filtering retains hidden checks.
  Downloads, photo scans and uploads process only checked rows currently shown.
- **Include / exclude by code prefix** changes matching bikes across the entire
  loaded list, including hidden rows. Enter `U9`, or paste several prefixes/full
  SKUs separated by commas, semicolons or whitespace. Matching ignores letter
  case. **Include codes** checks eligible matches; **Exclude codes** unchecks
  them. Enter still applies Exclude. Other checks remain unchanged. These actions
  change the current selection and are locked during jobs.
  Model copying offers the same action for whole TTCC groups, matching either
  the base code or any member SKU. It preserves sources and captured templates;
  excluded groups are omitted from source reads, copying, Continue and Retry.
  Copying also selects/unselects visible groups by source readiness or target
  results (failed, all copied or unfinished), without changing sources/templates.
- **Download selected** uses the chosen photos, description, specifications and
  tables in Missing or failed data or Refresh selected data mode. Missing mode
  skips current files, gives failed tables a fresh attempt, and respects terminal
  absence. Refresh invalidates only the chosen stages. Photos missing in Pimbo
  explicitly uses photos only and can find missing supplier links. The count is
  computed before starting; invalid or empty requests never expand to a whole run.
- **Upload selected** offers normal and Retry unfinished steps modes. Retry filters
  the existing checked rows; it never checks additional products. Existing Draft,
  target identity, save verification, colour, Custom photo and ordering checks apply.
- Uploads open a non-modal **Orbea upload run** board. Closing the board keeps the
  worker running; **Open run report** reopens it. The live view shows actual stage
  events, elapsed time, estimated time left and Stop after current product.
  The finished view separates Succeeded, Failed and Not started, labels warnings
  as a subset, groups identical causes, and shows each product's step results.
  Stop requests and browser-recovery failures explain why products were not run.
  Report retries use that run's targets and options; failed steps retain the
  existing verified-save resume rules. Excel export includes only the displayed
  run, including its not-started products, without importing older upload results.
  Full timestamped logs and JSON snapshots are saved in `upload-reports/` under
  the collection folder. Log filters, search, product grouping, Copy and Open log
  file share the same entries; raw Selenium details expand for the selected row.
- **Pimbo browsers** selects 1–4 sessions for uploads, source reading and model
  copying. The setting is shared between the upload and copying panels and
  defaults to one. Additional sessions use the selected Chrome, Firefox or Edge
  browser and the saved Pimbo login. All sessions must initialize before edits
  start. The app browser is reserved until all workers finish and is kept open;
  extra windows close afterward. Any unsafe browser remains open for review.
  Uploads keep all selected stages for a bike together. Rows sharing a known
  Pimbo ID stay in one task; verified IDs also prevent separate tasks from
  editing the same product. Copy workers take distinct TTCC groups, reserve
  verified target IDs globally and merge each confirmed result into one locked
  checkpoint. Stop finishes active products in every browser and starts no
  further products. Continue/Retry retain the existing verification rules.
- **Scan Pimbo**, **Scan Pimbo photos** and **Resume interrupted run** remain separate.
  Resume identifies the loaded interrupted run or asks for an explicit run folder.
  It never searches for a newer unrelated collection. The active job has one Stop.
- Extra tools contains one image form (URLs, destination and image types), plus
  description extraction and Excel sorting. Existing photo/table output settings
  supply the shared destination until `orbea_image_output` has been saved.

## Where changes belong

| Responsibility | Module |
| --- | --- |
| Screen assembly, settings, translations and report presentation | `GUI_Qt/screens/OrbeaScreen.py` |
| Source, filters, action, progress and product toolbar components | `GUI_Qt/orbea/panels.py` |
| Active source, selection snapshots, job ownership, startup and browser lease | `GUI_Qt/orbea/controller.py` |
| Explicit control locking while retaining table scrolling | `GUI_Qt/orbea/actions.py` |
| Product list, model filtering, upload choices and results | `GUI_Qt/orbea/upload.py` |
| Live/finished run boards and structured report data | `GUI_Qt/orbea/run_report.py`, `tools/orbea_automation/run_report.py` |
| Excel loading and read-only Pimbo photo checks | `GUI_Qt/orbea/photo_scan_workflow.py` |
| Direct tool presentation and compatibility adapters | `GUI_Qt/orbea/direct_workflow.py`, `description_workflow.py`, `photo_workflow.py`, `table_image_workflow.py` |
| Background execution and cancellation handshake | `GUI_Qt/orbea/workers.py` |
| Validated download requests and persisted queues | `tools/orbea_automation/selected_downloads.py` |
| Collection orchestration, checkpoints and partial results | `tools/orbea_automation/service.py` |
| Stage completeness, capture versions and local packages | `tools/orbea_automation/collection.py` |
| Saved Excel compatibility | `tools/orbea_automation/saved_collection.py`, `photo_scan.py` |
| Upload safety and shared stages | `tools/orbea_automation/upload.py`, `tools/supplier_upload.py` |

## Download scope and recovery

Photo matching uses its own narrowly scoped model aliases for WILD/M, RALLON/M,
RALLON 442/450 Enduro/DH and OIZ OMX+IL SL R+K. It reads fenced paint segments
directly and treats an explicit terminal Custom as a request for the untouched
Your Design gallery. Named paints still require one complete published paint
match; substring and SKU-suffix guesses are not accepted. Cinamon/Cinnamon is
the supported known spelling alias. This does not alter model-copy or
specification parsing. Partial collection logs include each stage's failure.

Geometry captures use the same `screenshot_element` routine as Size Tables for
each verified settings combination. Geometry's temporary viewport/scroll changes
keep the entire original table in the image, including native fonts, numbered
badges and configuration fields. They restore the original DOM and browser size
after capture or failure. The bike diagram is outside the geometry target;
Size Table capture is unchanged. Capture version 6 schedules older plain table
images for refresh on the next geometry download.

Old adjustable geometry PNGs remain old files until they are downloaded again;
uploading does not recapture their layout. Known older variant packages show
Geometry needs updating and block geometry upload before any Pimbo edit. Select
all affected products and use Missing or failed data with Geometry + CM size
tables to refresh their geometry while reusing the existing size-guide capture.
The current native styling is checked against real Occam, Wild, Rallon RS and
Rallon E-LTD DOM fixtures, including the 4, 12 and 48 configuration plans.
Repackaging refreshed tables invalidates the earlier attachment upload stages;
Retry unfinished steps must upload the new package before calling it finished.
Geometry replacement uploads at most twelve files per request, waits for all
cumulative attachments to resolve to permanent URLs, and rereads/clears the file
input between requests. A server error or a lost earlier attachment stops the
stage. A 48-file set is verified against native Firefox inputs and asynchronous
input replacement in an offline DOM fixture; the complete gallery is still
verified after saving/reload.

A product identity is its checkpoint path and row key, with a folder/SKU fallback
for legacy package-only folders. Selection resolution validates ownership, SKU,
Pimbo identity, source links and every run before a worker can mutate checkpoints.
Checkpoint rows without a completed local package remain available for collection.

`selected-downloads.json` stores the mode, stages, source root and ordered run/row
scope. Each participating checkpoint points to that queue. Its
`selected_download_operation` records the batch ID and whether refresh invalidation
has finished. Resume skips completed runs and preserves completed stages inside a
partially processed run. The original compatibility flags remain supported through
adapters; new UI actions must pass an explicit request.

## Lifecycle rules

- Start every Orbea job through `OrbeaWorkflowController.start_job`, passing a
  worker factory. Construction, registration and thread-start errors must follow
  the same cleanup path: clear ownership, finish any registered activity, restore
  controls and release the acquired browser lease once.
- Ownership lasts until queued results and the finished callback have run on the
  UI thread. `isRunning() == False` alone must never unlock product selection.
  Shutdown drains queued callbacks after waiting for workers; never terminate them.
- Lock checkboxes, selection menus, model filters and configuration explicitly.
  Keep the product table enabled for scrolling. Disable Stop after requesting it.
- Each worker retains one cancellation token. A stop during service construction
  reaches that service and preserves usable partial results and saved checkpoints.
- Direct tool adapters delegate lifecycle management to the shared controller.
  Service factories may still be classes, callables or supported instances.
- Collection cleanup preserves the original error and partial reports. Release
  collection locks in `finally` even when reporting fails. Processing completion
  does not imply every source file was available or every upload succeeded.

## Model-copy workflow

`GUI_Qt/orbea/model_copy.py` owns the third Orbea tab. Its worker runs through
`OrbeaWorkflowController.start_job`, sharing browser ownership and queued cleanup
with existing jobs. Stop is checked between products, not during translation/save.
`GUI_Qt/orbea/model_copy_groups.py` presents one row per bike, with a merged TTCC
cell and an exclusive source selector per group. Source changes use the existing
checkpoint service; clicking the selected source preserves its captured template.
Filters hide whole groups, retain hidden checks and restrict actions to visible
groups. All source and selection controls remain locked through queued cleanup.
The panel shares `WorkspaceColumns`, screen cards and table themes with Orbea.
Source reads return to the product list after inspection. The UI logs a source's
outcome only after its checkpoint is written, then distinguishes source-reading
completion from copying/saving. Summary counts use the selected groups; stopped
runs include unread groups and worker errors preserve their failure message.
`tools/orbea_automation/model_copy.py` owns typed source snapshots, exact TTCC
groups, independent version-1 checkpoints, saved-result verification and exports.
`Managers/PimboChoices.py` adds bounded DOM readers and existing-option selection
to `PimboProductEditor`; never widen an attribute popup lookup to unrelated fields.
Attribute labels must exclude empty Base UI dropdown buttons and addons even
when they have `font-medium`. Ignore aria-hidden companion inputs when finding
row boundaries, and exclude popup searches/options from attribute discovery.
The reduced live markup in `pimbo_attribute_input_groups.html` covers this shape.
Category removal must use selected chips' controls or explicitly labelled
removal buttons, never a generic header icon (which may invoke MagicAI).
Categories may use a permanent list of `div[role="button"]` rows; resolve this
within the category field, with exact full-path labels. Attribute inputs still
require their own dropdown. `pimbo_category_card.html` covers the live header,
chips, inline category list and neighbouring fields without editing Pimbo.

Basic Info fields can be ready before HugeRTE mounts its iframe or loads its
saved HTML. `description_html` waits for an editable body and restores the
top-level frame after every attempt. Source capture uses `require_content=True`
to wait through the initially blank body; ordinary reads still accept a ready,
empty editor. `test_pimbo_description_loading.py` covers delayed content,
replaced frames, empty editors and preserved HTML formatting.

Tests in `test_orbea_model_copy.py`, `test_pimbo_copy_choices.py`, and
`test_orbea_model_copy_ui.py` exercise complete copying, delayed hydration,
multi-select sets, source changes, retries, shutdown/startup ownership and locale
labels without connecting to live Pimbo.

## Verification

The **Orbea download browsers** control beside the source download choices
shares the 1–4 browser count with uploads and copying. Initial Pimbo scanning
and Orbea URL lookup remain serial; selected public-site downloads use separate
owned sessions for different model pages. A model's colour photos, native
geometry configurations, CM size table and selected source text stay together.
Shared URLs, SKUs and existing package folders belong to one task. Each session
is created, used and closed by its own thread, with distinct browser profiles;
the authenticated Pimbo browser is never borrowed for downloads.

Workers merge only their owned rows/images into the main checkpoint. Report
and shared immutable photo-cache writes are serialized. Stop prevents queued
models from starting and retains completed stages for Resume/Missing; Refresh
keeps its existing invalidation rules. Browser startup/access failures stop
the queue and preserve the partial report. The count can change on Resume
without invalidating saved matches. Offline concurrency coverage is in
`test_orbea_parallel_downloads.py`.

**Publish products: Draft → Published** is an optional Pimbo workflow stage,
disabled by default. It forces Save and runs last, after both content and
specification saves. It can run alone on selected scanned/collected products or with
uploads; failures in any other selected stage block publication. Full variant
SKU lookup, package identity, browser reservations and parallel product claims
remain in effect. Existing unsaved edits block a publication run. The editor
selects the exact Published option from the Status dropdown, checks the version
increment and reloads to verify persistence. Already Published products in a
publication-only run are rechecked without another Save. In Review and Disabled
products stay blocked. Results and retry filtering include publication as a
separate stage. Offline coverage is in `test_orbea_publishing.py`.

Run offline fixtures and mocked services; acceptance never edits live Pimbo:

```powershell
$env:NODE_OPTIONS='--preserve-symlinks-main'
.\.venv\Scripts\python.exe -m pytest tests -k "orbea or product_data_safety or pimbo_workflow or specification_ai_exclusions" -q
.\.venv\Scripts\python.exe tools\smoke_imports_ui.py
```

The Node flag lets the existing DOM fixture run from linked Windows workspaces.
`test_orbea_workflow_refactor.py` covers all startup failure phases, queued cleanup,
checked-only retry, download modes/stages, incomplete packages, multi-run recovery,
exhausted retries, stale table captures and shutdown. The existing selection,
collection, colour, Custom photo, ordering, identity, Draft, upload-history and save
verification suites remain regression coverage. Check both languages at wide and
narrow widths, including the menus, one visible Stop and the shared image form.

Cross-supplier cancellation and remaining app-wide presentation debt are outside
this Orbea refactor; TD-024 and TD-035 should not be closed solely on this change.

When Excel holds an existing report open, automatic report updates save
`orbea_matches_updated.xlsx` beside it. If that copy is also open, a numbered
copy is used. The checkpoint remembers the latest report, and **Open Excel**
uses that path. Further updates stay in the copy, preserving the workbook
the operator has open, including subsequent manual edits. Reading a source
workbook uses its last saved contents; unsaved changes in Excel are not visible
to the app.
