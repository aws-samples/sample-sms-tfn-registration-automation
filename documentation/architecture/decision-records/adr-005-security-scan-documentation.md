<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# ADR-005: Security Scan Results Not Bundled in Repository

**Status:** Accepted
**Date:** 2026-04-29
**Deciders:** Project team
**Finding Severity:** Low
**Source:** Holmes security scan

## Context

Holmes security scan flagged missing security scan results documentation. The scanner
expected scan reports to be committed to the repository for traceability and audit
purposes.

During the security review process, scanning tools generated detailed reports
containing findings, rule IDs, scanner-specific metadata, and account-specific
details. The question arose whether these scan results should be committed to the
repository.

## Decision

Security scan results are stored locally in `security-scans/` (gitignored) and are
not committed to the repository. This is by design.

Reasons:

1. **Internal tool references.** Scan results contain internal scanner tool names,
   rule IDs, and scanner-specific metadata that should not appear in public
   repositories. This project is intended for publication to aws-samples.
2. **Account-specific details.** Scan reports may reference AWS account IDs, region
   names, and resource ARNs from the test environment.
3. **Point-in-time artifacts.** Scan results reflect the state of the code at scan
   time and become stale as code changes. They are not durable documentation.
4. **ADRs provide durable documentation.** All findings have been addressed through
   code fixes or documented as accepted risks in these Architecture Decision Records.
   The ADRs provide sufficient context to understand each decision without needing
   the original scan output.

## Consequences

### Positive
- No internal tool names, scanner rule IDs, or account-specific details are exposed in the public repository.
- ADRs provide durable, human-readable documentation of all security decisions.
- Code fixes addressing findings are visible in the git history.

### Negative
- No raw scan output is available in the repository for independent verification.
- Future reviewers cannot see the original scanner output or rule IDs.

### Neutral
- Scan results are retained locally (outside the repository) in the `security-scans/` directory for internal audit purposes.
- The `.gitignore` file excludes the `security-scans/` directory from version control.

### Review Trigger
- Re-evaluate if a mechanism exists to sanitize scan results of internal tool names and account details before publication.
- Re-evaluate if the repository moves to a private hosting model where internal references are acceptable.

## ADRs Documenting Scan Findings

The following ADRs document all accepted risks and false positives from the Holmes
security scan:

| ADR | Finding | Disposition |
|-----|---------|-------------|
| [ADR-001](adr-001-iam-resource-wildcards.md) | IAM `Resource: '*'` for EUM SMS and Step Functions actions | Accepted risk — service limitation |
| [ADR-002](adr-002-eum-sms-service-name.md) | "AWS End User Messaging SMS" not in service registry | False positive — correct service name |
| [ADR-003](adr-003-s3-mfa-delete.md) | Missing MFA Delete on S3 buckets | Accepted risk — cannot enable via CloudFormation |
| [ADR-004](adr-004-registration-lambda-error-handling.md) | Missing try/except in Registration Lambda | By design — Step Functions error routing |
| [ADR-005](adr-005-security-scan-documentation.md) | Missing scan results in repository | By design — internal tool references |
| [ADR-006](adr-006-code-scan-attestation.md) | Missing second-party verification attestation | Accepted — Holmes review process provides verification |
| [ADR-007](adr-007-access-logging-scope.md) | CloudTrail and API Gateway logging not enabled by default | By design — account-level config, cost-sensitive |
| [ADR-008](adr-008-logs-bucket-self-logging.md) | Access logs bucket lacks its own logging | Accepted — circular logging, minimal risk |

## Alternatives Considered

### Option 1: Include redacted scan results
- **Effort:** Medium
- **Why rejected:** Redacting internal tool names and rule IDs from scan output is
  error-prone. Partially redacted reports provide limited value and risk accidental
  disclosure of internal information.

### Option 2: Include scan results in a private branch
- **Effort:** Low
- **Why rejected:** The repository is intended for public publication. Private branches
  add complexity and may be accidentally merged or exposed.

### Option 3: Include only the scan summary (pass/fail counts)
- **Effort:** Low
- **Why rejected:** Summary counts without context are not useful. The ADRs provide
  better documentation of each finding and its resolution.

## References

- [AWS Samples Contributing Guidelines](https://github.com/aws-samples/.github/blob/main/CONTRIBUTING.md)
- [Security Design Document](../toll-free-registration-automation-security-design.md)
