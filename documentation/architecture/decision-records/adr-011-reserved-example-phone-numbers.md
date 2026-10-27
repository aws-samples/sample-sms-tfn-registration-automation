<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# ADR-011: Example Phone Numbers Use the NANP Reserved Range

**Status:** Accepted
**Date:** 2026-08-12
**Deciders:** Project team
**Finding Severity:** High (scanner classification)
**Source:** Holmes security scan

## Context

Test fixtures, sample events, and front-end placeholders carried numbers like
`+12065551234` and `+18885551234`. They look invented, and the `555` exchange is
widely assumed to be safe, but only a narrow slice of it actually is: the North
American Numbering Plan reserves `555-0100` through `555-0199` for fictional
use. Everything else in the `555` exchange, `555-1234` included, can be and in
some area codes has been assigned to a real subscriber.

Holmes raised five High findings under Sensitive Data Handling for numbers
outside that reserved block. Publishing a sample that tells readers to text an
arbitrary number is a real risk, not a scanner technicality.

## Decision

Every phone number that appears anywhere in this repository sits inside
`555-0100` to `555-0199`.

| Old | New | Where |
|-----|-----|-------|
| `+12065551234` | `+12065550142` | Contact and support numbers in fixtures, sample events, wizard placeholder |
| `+18885551234` | `+18885550142` | Toll-free number in unit test seed data |
| `+18885550001` | `+18885550101` | Toll-free number in registration test seed data |
| `+15551234567` | `+12065550142` | Destination number in the generated test-message CLI command |

`+18005550199` and `+18885550199`, already inside the range, are unchanged.

## Consequences

### Positive
- Copy-pasting any command from this sample cannot reach a real subscriber
- Resolves all five High findings without a documented exception

### Negative
- The numbers read as less obviously placeholder to anyone who does not know the
  reserved range, which is why this record exists

### Convention for contributors
New phone numbers must match `+1<area>555 01XX`. `+12065550142` is the default
for a contact number and `+18885550142` for a toll-free number. There is no
automated check for this, so it is worth a look during review.

## References
- [NANP: fictitious telephone numbers](https://en.wikipedia.org/wiki/555_(telephone_number))
- [Security Design Document](../toll-free-registration-automation-security-design.md)
