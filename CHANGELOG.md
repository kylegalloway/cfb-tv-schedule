# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- Initial scraper for fbschedules.com and NCAA.com college football TV
  schedules, with cross-checking between the two sources and a fallback
  path when one source is degraded.
- Flask dashboard app (`app.py`) serving the cached schedule, a manual
  refresh endpoint, and a background APScheduler auto-refresh job.
- Static sortable/filterable table UI (`static/`).
- Test suite covering parsing fixtures, fallback logic, cross-checking,
  and an opt-in live canary suite against the real sites.
- Dockerfile for containerized deployment.
- Apache License 2.0.
