# ADR-001: Google-style docstrings

- **Status:** Accepted
- **Date:** 2026-10-24

## Context
The project requires good docstrings in all Python code. v0.1.5 mixes reST
(`:param x:`) in most files with free-form text in others, and about 30 functions and
13 of 22 modules have none. A single style is needed so docs can be generated and
linted.

## Decision
Use Google-style docstrings (`Args:`, `Returns:`, `Raises:`, `Example:`) for every
module, class, and public function. Enforce with ruff's `pydocstyle` rules using
`convention = "google"`.

## Consequences
- Existing reST docstrings are converted when each module is reworked in v0.2.0.
- CONVENTIONS.md § Docstrings holds the templates.
- Sphinx (napoleon) or MkDocs (mkdocstrings) can render them later without changes.
