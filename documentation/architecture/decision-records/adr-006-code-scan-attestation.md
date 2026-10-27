<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# ADR-006: Code Scan Attestation and Second-Party Verification

**Status:** Accepted
**Date:** 2026-04-29
**Deciders:** Project team
**Finding Severity:** High (scanner classification)
**Source:** Holmes security scan

## Context

Holmes security scan requires second-party verification attestation for compensating
controls and evidence that updated scans verified mitigation effectiveness. The scan
results themselves are stored locally and not committed to the repository (see ADR-005).

## Decision

Accept this finding. The security review process for this project follows the standard
Holmes Content Security Review workflow:

1. Code is scanned via Holmes portal upload
2. Findings are addressed through code fixes or documented as ADRs
3. Re-scans verify that code fixes are effective
4. ADRs serve as the durable documentation of accepted risks

The scan-rescan cycle itself constitutes verification of mitigation effectiveness.
Each ADR documents the finding, the decision, and the compensating controls. The
Holmes review process provides the second-party verification through the reviewer
who approves the final scan.

## Consequences

### Positive
- All findings are documented in ADRs with clear rationale
- Code fixes are verifiable through git history
- The Holmes review process provides external verification

### Negative
- No formal attestation document exists separate from the ADRs
- Scan results are not committed to the repository (see ADR-005)

## References

- [ADR-005: Security Scan Documentation](adr-005-security-scan-documentation.md)
- [Security Design Document](../toll-free-registration-automation-security-design.md)
