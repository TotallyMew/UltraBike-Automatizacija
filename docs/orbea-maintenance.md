# Maintaining the Orbea workflow

The Automation page builds its source, filter, selection, action and progress
panels directly in their final layout. Do not add a build-and-reparent pass:
locking belongs to the workflow controller, including controls in other columns.
Existing service entry points, saved checkpoints and output formats remain
supported; the photo-only selected-download entry point is an adapter.

## User workflow

- **Load products** opens an Excel, a saved folder, or reloads the displayed source.
  Scan results load automatically. The source path stays visible below the filters.
- **Selection** offers Select visible, Clear visible and additive Add by status,
  including No photos. Model filtering retains hidden checks. Downloads, photo
  scans and uploads process only checked rows currently shown.
- **Download selected** uses the chosen photos, description, specifications and
  tables in Missing or failed data or Refresh selected data mode. Missing mode
  skips current files, gives failed tables a fresh attempt, and respects terminal
  absence. Refresh invalidates only the chosen stages. Photos missing in Pimbo
  explicitly uses photos only and can find missing supplier links. The count is
  computed before starting; invalid or empty requests never expand to a whole run.
- **Upload selected** offers normal and Retry unfinished steps modes. Retry filters
  the existing checked rows; it never checks additional products. Existing Draft,
  target identity, save verification, colour, Custom photo and ordering checks apply.
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
| Excel loading and read-only Pimbo photo checks | `GUI_Qt/orbea/photo_scan_workflow.py` |
| Direct tool presentation and compatibility adapters | `GUI_Qt/orbea/direct_workflow.py`, `description_workflow.py`, `photo_workflow.py`, `table_image_workflow.py` |
| Background execution and cancellation handshake | `GUI_Qt/orbea/workers.py` |
| Validated download requests and persisted queues | `tools/orbea_automation/selected_downloads.py` |
| Collection orchestration, checkpoints and partial results | `tools/orbea_automation/service.py` |
| Stage completeness, capture versions and local packages | `tools/orbea_automation/collection.py` |
| Saved Excel compatibility | `tools/orbea_automation/saved_collection.py`, `photo_scan.py` |
| Upload safety and shared stages | `tools/orbea_automation/upload.py`, `tools/supplier_upload.py` |

## Download scope and recovery

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
