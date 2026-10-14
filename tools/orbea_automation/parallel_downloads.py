"""Owned public-site sessions; isolated rows with serialized checkpoint/report writes."""
from __future__ import annotations

from copy import deepcopy
import threading

from .catalogue import normalize_code
from .checkpoint import RunCheckpoint
from .collection import missing_downloads
from .models import RunCancelled, OrbeaDownloadSessionError
from .report import write_image_manifest, write_report
from .utils import canonicalize_url


def download_groups(rows):
    """Keep shared URLs, SKUs and existing package folders under one owner."""
    parents = list(range(len(rows)))

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    owners = {}
    for index, row in enumerate(rows):
        keys = [("url", canonicalize_url(row.get("catalogue_url"))), ("sku", normalize_code(row.get("sku")))]
        if row.get("local_folder"):
            keys.append(("folder", str(row["local_folder"]).replace("\\", "/").casefold()))
        for key in keys:
            if not key[1]:
                continue
            if key in owners:
                parents[root(index)] = root(owners[key])
            owners[key] = index
    groups = {}
    for index, row in enumerate(rows):
        groups.setdefault(root(index), []).append(row)
    return tuple(tuple(group) for group in groups.values())


class _QueueToken:
    def __init__(self, token, fatal):
        self.token, self.fatal = token, fatal

    def is_cancelled(self):
        check = getattr(self.token, "is_cancelled", None) or getattr(self.token, "is_set", None)
        return self.fatal.is_set() or bool(check and check())

    is_set = is_cancelled


class _CheckpointView(RunCheckpoint):
    def __init__(self, owner, rows):
        with owner.lock:
            super().__init__(owner.checkpoint.path, deepcopy(owner.checkpoint.data), resumed=owner.checkpoint.resumed)
        self.owner = owner
        self.keys = {row["row_key"] for row in rows}
        self.urls = {canonicalize_url(row["catalogue_url"]) for row in rows}
        self.data["selected_download_row_keys"] = list(self.keys)

    def save(self):
        """Merge only this task's rows and image records, including partial stages."""
        with self.owner.lock:
            target = self.owner.checkpoint
            by_key = {row["row_key"]: row for row in target.results}
            for row in self.results:
                if row.get("row_key") in self.keys:
                    original = by_key[row["row_key"]]
                    original.clear()
                    original.update(deepcopy(row))
            for url in self.urls:
                if url in self.images:
                    target.images[url] = deepcopy(self.images[url])
            if not self.data.get("website_lookup_completed", True):
                target.data["website_lookup_completed"] = False
            target.save()


class _QuietProgress:
    def emit(self, *_args):
        # Stage helpers have local row/URL totals. The owner reports the actual
        # completed bike count, keeping progress monotonic across browsers.
        pass


class _DownloadQueue:
    def __init__(self, service, config, checkpoint, reporter, token, log, rows, pending_by_url, retry_failed):
        self.service, self.config, self.checkpoint, self.reporter = service, config, checkpoint, reporter
        self.log, self.pending_by_url, self.retry_failed = log, pending_by_url, retry_failed
        self.lock = threading.RLock()
        self.fatal = threading.Event()
        self.token = _QueueToken(token, self.fatal)
        self.tasks = download_groups(rows)
        self.index = self.finished = 0
        self.total = len(rows)
        self.errors = []
        self.resources = []

    def claim_resource(self, resource):
        with self.lock:
            if any(resource is old for old in self.resources) or resource is self.service.pimbo_driver:
                raise OrbeaDownloadSessionError("Parallel Orbea downloaders must have separate owned browser sessions")
            self.resources.append(resource)

    def completed_bike(self, row, number, *, skipped=False):
        with self.lock:
            self.finished += 1
            write_image_manifest(self.checkpoint)
            write_report(self.checkpoint)
            detail = "already complete" if skipped else row.get("collection_status", "checked")
            self.reporter.emit("product_data", self.finished, self.total,
                f"[Orbea browser {number}] {row['sku']}: {detail}")

    def access_progress(self, number, waiting, message):
        with self.lock:
            self.service._log(self.log, f"[Orbea browser {number}] {message}")
            self.reporter.emit("website_access" if waiting else "product_data", self.finished,
                self.total, f"[Orbea browser {number}] {message}")

    def work(self, number):
        from .service import OrbeaAutomationService
        from .website import OrbeaWebsiteClient
        child = OrbeaAutomationService(None, image_driver_factory=self.service.image_driver_factory,
            photo_service_factory=self.service.photo_service_factory,
            website_client_factory=self.service.website_client_factory)
        child._public_profile_slot = number
        child._public_driver_claim = self.claim_resource
        website = None
        owns_website = False

        def new_driver():
            child._check_cancelled(self.token)
            return child._new_image_driver(self.config)

        def log(message):
            child._log(self.log, f"[Orbea browser {number}] {message}")

        def new_photos():
            from .photos import OrbeaPhotoService
            factory = self.service.photo_service_factory or OrbeaPhotoService
            photos = factory()
            self.claim_resource(photos)
            return photos

        child.photo_service_factory = new_photos

        try:
            child._check_cancelled(self.token)
            factory = child.website_client_factory or OrbeaWebsiteClient
            website = factory(new_driver, self.token, self.config.navigation_timeout)
            self.claim_resource(website)
            owns_website = True
            child._website_client = website
            website.access_progress = lambda waiting, message: self.access_progress(number, waiting, message)
            while True:
                with self.lock:
                    if self.token.is_cancelled() or self.index >= len(self.tasks):
                        return
                    rows = self.tasks[self.index]
                    self.index += 1
                view = _CheckpointView(self, rows)
                product_cache, photo_cache = {}, {}
                try:
                    for row in view.download_rows:
                        child._check_cancelled(self.token)
                        child._collect_website_product(website, self.config, view, _QuietProgress(), self.token, log, row,
                            retry_failed=self.retry_failed, pending_by_url=self.pending_by_url,
                            product_cache=product_cache, photo_cache=photo_cache, refresh_reports=False)
                        self.completed_bike(row, number)
                finally:
                    view.save()
        except RunCancelled:
            if not self.token.is_cancelled():
                with self.lock:
                    self.errors.append(RunCancelled("An Orbea downloader stopped before completing its bike"))
                    self.fatal.set()
        except BaseException as error:
            with self.lock:
                self.errors.append(error)
                self.fatal.set()
        finally:
            if owns_website:
                try:
                    website.close()
                except BaseException as error:
                    with self.lock:
                        self.errors.append(error)
                        self.fatal.set()

    def run(self):
        count = min(self.config.download_browser_count, len(self.tasks))
        self.service._log(self.log, f"Downloading with {count} Orbea browsers across {len(self.tasks)} model groups")
        threads = []
        try:
            for number in range(1, count + 1):
                thread = threading.Thread(target=self.work, args=(number,), name=f"Orbea-Download-{number}")
                thread.start()
                threads.append(thread)
        except BaseException as error:
            self.errors.append(error)
            self.fatal.set()
        finally:
            for thread in threads:
                thread.join()
        if self.errors:
            raise self.errors[0]
        if self.token.is_cancelled():
            raise RunCancelled("The parallel Orbea download was stopped; completed stages are saved")


def collect_parallel_packages(service, website, config, checkpoint, reporter, token, log, rows, *, pending_by_url, retry_failed):
    """Keep lookup serial, then distribute independent model pages to owned threads."""
    previous_driver = getattr(website, "_driver", None)
    website.close()
    service._website_client = None
    pending = []
    already_complete = []
    for row in rows:
        if config.downloads_only and not missing_downloads(row, config, checkpoint.run_dir):
            if config.download_product_photos:
                from .photo_packages import package_folder
                package_folder(checkpoint, row)
            already_complete.append(row)
        else:
            pending.append(row)
    queue = _DownloadQueue(service, config, checkpoint, reporter, token, log, pending, pending_by_url, retry_failed)
    queue.resources.append(website)
    if previous_driver is not None:
        queue.resources.append(previous_driver)
    queue.total = len(rows)
    queue.finished = len(already_complete)
    if already_complete:
        reporter.emit("product_data", queue.finished, len(rows), f"{len(already_complete)} bikes already have the selected downloads")
    if not pending:
        return
    service._parallel_downloading = True
    try:
        queue.run()
    finally:
        service._parallel_downloading = False
