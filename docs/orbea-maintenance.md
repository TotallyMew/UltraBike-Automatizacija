# Maintaining the Orbea workflow

The collection formats, supplier services and screen entry points remain compatible
with saved collections. UI jobs have separate controllers so that changes to one
download tool do not require copying the lifecycle of the others.

## Where changes belong

| Responsibility | Module |
| --- | --- |
| Layout, controls, settings, report preview, collection/resume presentation | `GUI_Qt/screens/OrbeaScreen.py` |
| Active job ownership and locking all job inputs | `GUI_Qt/orbea/actions.py` |
| Construction of collection/description/photo/table services and Pimbo lease | `GUI_Qt/orbea/controller.py` |
| Signal connections, start failure recovery and control restoration for direct jobs | `GUI_Qt/orbea/direct_workflow.py` |
| Description validation, progress and result presentation | `GUI_Qt/orbea/description_workflow.py` |
| Photo validation, progress and result presentation | `GUI_Qt/orbea/photo_workflow.py` |
| Table/image validation, progress and result presentation | `GUI_Qt/orbea/table_image_workflow.py` |
| Background execution and shared cancellation handshake | `GUI_Qt/orbea/workers.py` |
| Collection orchestration, checkpoints, owned browser cleanup and partial results | `tools/orbea_automation/service.py` |
| Description/specification/photo/table stage collection and completeness | `tools/orbea_automation/collection.py` |
| Saved Excel collection import/reconnection | `tools/orbea_automation/saved_collection.py` |
| Product matching, source parsing and public website access | `tools/orbea_automation/website.py` |
| Local package selection and Pimbo upload UI | `GUI_Qt/orbea/upload.py` |
| Orbea upload rules and shared upload stages | `tools/orbea_automation/upload.py`, `tools/supplier_upload.py` |

## Lifecycle rules

- A screen owns a job until its **finished callback** has applied the queued
  results on the UI thread. A thread stopping is not sufficient to release it.
- Lock all collection/direct-download/upload inputs through `set_controls_locked`.
  Keep only the active job's Stop available; disable it after a stop request.
  The upload panel manages its own controls while it is the active job.
- Each service worker keeps one `CancellationToken`. Stop before or during service
  construction reaches the constructed service once and does not replace the token.
  Cancelled jobs may return completed files/checkpoints; keep those results.
- Direct job controllers inherit `OrbeaDirectWorkflow`. Let it connect signals,
  track the worker and restore controls rather than duplicating those steps.
- Service factories may be classes, callables or supported service instances.
  Choose a supported signature before calling a browser factory; an internal
  `TypeError` must never trigger a second browser construction.
- Collection cleanup preserves the original error and usable partial reports.
  Release the collection lock in a `finally` block even if cleanup/reporting fails.
- Display failed descriptions as partial completion, and keep saved files available.
  Completion of processing does not mean every source URL succeeded.

## Verification

Use the offline tests; these commands do not edit live Pimbo products:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -k "orbea or product_data_safety or pimbo_workflow or specification_ai_exclusions" -q
.\.venv\Scripts\python.exe tools\smoke_imports_ui.py
```

`test_orbea_workers.py` covers service construction and cancellation races.
`test_orbea_run_cleanup.py` covers cleanup/report errors, lock recovery and browser
factory contracts. Direct-job ownership, controls and partial-result regressions
are in `test_orbea_upload_ui.py`; the existing description/photo/table/collection
tests exercise the extracted controllers through the unchanged screen entry points.

The screen still owns substantial layout, translation, settings and collection
presentation. TD-024 and TD-035 remain open for that work and shared cancellation
across other supplier workflows; this refactor completes the Orbea direct-job portion.
