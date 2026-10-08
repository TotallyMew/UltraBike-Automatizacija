"""Keep a PIMBO job's browser available until work and review are finished."""

from Managers.PimboProductEditor import PimboProductEditor


def product_work_is_active(main, worker=None, session_manager=None):
    if worker is not None and worker.isRunning():
        return True
    drivers = [getattr(main, "driver", None)]
    drivers.extend(session.driver for session in getattr(session_manager, "sessions", ()))
    for driver in drivers:
        if driver is None:
            continue
        if "/dashboard/products/" in str(driver.current_url or ""):
            if PimboProductEditor(driver).is_dirty():
                return True
    return False


def acquire_product_browser(main, owner, worker=None, session_manager=None):
    owner_getter = getattr(main, "browser_lease_owner", None)
    if owner_getter and owner_getter() not in (None, owner):
        return False
    if product_work_is_active(main, worker, session_manager):
        return False
    acquire = getattr(main, "try_acquire_browser_lease", None)
    return bool(acquire(owner)) if acquire else True


def release_product_browser(main, owner, worker=None, session_manager=None):
    if product_work_is_active(main, worker, session_manager):
        return False
    release = getattr(main, "release_browser_lease", None)
    if release:
        release(owner)
    return True
