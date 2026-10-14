"""Merge per-group copy progress into one serialized, resumable checkpoint."""
from copy import deepcopy
from threading import RLock

from .model_copy import OrbeaCopyRunResult, OrbeaModelCopyService, load_copy_workbook


class ModelCopyCheckpoint:
    def __init__(self, workbook, *, capture=False, mapping_changed=None):
        self.workbook = workbook
        self.lock = RLock()
        path = OrbeaModelCopyService.checkpoint_path(workbook)
        if capture:
            try:
                self.state = OrbeaModelCopyService.load_checkpoint(workbook)
            except (OSError, ValueError, KeyError, TypeError):
                self.state = OrbeaCopyRunResult(load_copy_workbook(workbook), [], path)
        else:
            self.state = OrbeaModelCopyService.load_checkpoint(workbook)
        templates = {group.ttcc: group.template for group in self.state.groups}
        self.claimed = {item.product_id for item in self.state.results if item.status == "saved" and item.product_id
                        and not (mapping_changed and mapping_changed(item, templates.get(item.ttcc)))}

    def snapshot(self):
        with self.lock:
            return deepcopy(self.state)

    def claim(self, product_id):
        with self.lock:
            if product_id in self.claimed:
                return False
            self.claimed.add(product_id)
            return True

    def persist(self, scope, groups, results):
        with self.lock:
            updates = {group.ttcc: deepcopy(group) for group in groups if group.ttcc in scope}
            self.state.groups = [updates.get(group.ttcc, group) for group in self.state.groups]
            self.state.results = ([item for item in self.state.results if item.ttcc not in scope]
                                  + [deepcopy(item) for item in results if item.ttcc in scope])
            OrbeaModelCopyService._write(self.state.checkpoint_path, self.workbook,
                                        self.state.groups, self.state.results)
