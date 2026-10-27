<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# ADR-010: Wizard Front End Runs Without 'unsafe-inline'

**Status:** Accepted
**Date:** 2026-08-12
**Deciders:** Project team
**Finding Severity:** High (scanner classification)
**Source:** Holmes security scan

## Context

The wizard shipped as a single self-contained HTML file with its CSS in a
`<style>` block, its JavaScript in a `<script>` block, inline `onclick`,
`oninput`, and `onchange` attributes, and inline `style` attributes. To make that
work, the page declared:

```
default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'
```

Holmes flagged the `'unsafe-inline'` in `script-src` as High. The directive
disables the main protection a CSP provides: with it present, any injected
`<script>` or event-handler attribute executes.

The single-file packaging was deliberate. The wizard is meant to be opened
directly from disk with no build step and no server.

## Decision

Split the page into three files that still work over `file://` with no build
step, and drop `'unsafe-inline'` from both directives.

- `frontend/toll-free-registration-wizard.html` holds markup only
- `frontend/wizard.css` holds all styles, including utility classes that replace
  the former inline `style` attributes
- `frontend/wizard.js` holds all logic plus a `DOMContentLoaded` block that
  attaches every handler with `addEventListener`

Markup declares intent through data attributes that the wiring block reads:
`data-goto-step`, `data-action` (`next`, `prev`, `copy-all`,
`toggle-company-id`), and `data-char-count`. Showing and hiding the company
identifier fields toggles a `hidden` class rather than assigning
`element.style.display`.

The policy is now:

```
default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'
```

`object-src 'none'` and `base-uri 'none'` were added while the directive was
being edited. Neither is needed by the page, and both close off common injection
paths.

## Consequences

### Positive
- An injected script tag or handler attribute will not execute
- Styles and logic are easier to read and diff than a 969-line single file
- Resolves the High finding without a documented exception

### Negative
- Three files to copy instead of one. Opening the HTML without the two siblings
  alongside it yields an unstyled, inert page.

## References

- [MDN: Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy)
- [Security Design Document](../toll-free-registration-automation-security-design.md)
