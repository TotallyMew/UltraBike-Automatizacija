"""Match Orbea views to Pimbo media without relying on thumbnail appearance."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

VIEWS = ("side", "front", "back")


def photo_view(path):
    stem = Path(unquote(urlsplit(str(path)).path)).stem.casefold()
    match = re.search(r"(?:^|[_-])(side|front|back)$", stem)
    return match.group(1) if match else ""


def photo_sort_key(path):
    view = photo_view(path)
    return (VIEWS.index(view) if view else len(VIEWS), Path(path).name.casefold())


def desired_photo_order(sources, paths):
    """Return all current photos, putting matched side/front/back views first."""
    sources = tuple(sources)
    if not sources or len(set(sources)) != len(sources):
        raise ValueError("The Pimbo gallery is empty or has duplicate photo URLs")
    identities = {}
    for path in paths:
        view = photo_view(path)
        if not view:
            continue
        path = Path(path)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        for identity in (digest, path.stem.casefold()):
            if identity in identities and identities[identity] != view:
                raise ValueError("The same Orbea photo matches different views")
            identities[identity] = view
    matched = {view: [] for view in VIEWS}
    extras = []
    for source in sources:
        identity = Path(unquote(urlsplit(source).path)).stem.casefold()
        view = identities.get(identity)
        (matched[view] if view else extras).append(source)
    missing = [view for view in VIEWS if not matched[view]]
    if missing:
        raise ValueError("Could not match uploaded Orbea views: " + ", ".join(missing) + ". Keep the original collected photos in this product folder.")
    return tuple(source for view in VIEWS for source in matched[view]) + tuple(extras)
