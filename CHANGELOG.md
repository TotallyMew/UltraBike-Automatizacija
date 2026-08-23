# Changelog

This file records shipped UltraBike Automatizacija behavior. Release manifests
are generated from the installer and are not a substitute for this history.

## Unreleased

### Changed

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
