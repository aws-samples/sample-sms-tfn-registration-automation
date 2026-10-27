<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# ADR-003: Skip MFA Delete on S3 Buckets

**Status:** Accepted
**Date:** 2026-04-29
**Deciders:** Project team
**Finding Severity:** Medium
**Source:** Holmes security scan

## Context

Holmes security scan flagged missing MFA Delete on the `UploadBucket`. MFA Delete
requires multi-factor authentication for:

- Changing the versioning state of a bucket
- Permanently deleting an object version

This control prevents accidental or malicious deletion of objects and protects the
versioning configuration from being disabled.

## Decision

Skip MFA Delete on S3 buckets for this project.

Reasons:

1. **Cannot be enabled via CloudFormation/SAM.** MFA Delete requires the AWS CLI or
   SDK using root account credentials. There is no CloudFormation property to enable it.
2. **Requires root account credentials.** Root credentials should not be used
   programmatically or stored in deployment pipelines. This is a security anti-pattern.
3. **Sample/demo solution.** This is not a production system managing long-term
   sensitive data. The upload bucket stores transient registration attachments
   (opt-in screenshots, T&C documents) that are auto-deleted after 90 days.
4. **Compensating controls are in place.** See below.

## Consequences

### Positive
- Deployment remains fully automated via `sam deploy` with no manual post-deployment steps.
- No root account credentials are needed in the deployment workflow.

### Negative
- S3 objects can be permanently deleted without MFA verification.
- Bucket versioning can be suspended without MFA verification.

### Neutral
- Users who adapt this solution for production can enable MFA Delete manually as a post-deployment step using root credentials.

### Compensating Controls in Place

| Control | Status |
|---------|--------|
| S3 versioning | Enabled — protects against accidental overwrites |
| Block Public Access | Enabled on all 4 settings — prevents public exposure |
| TLS enforcement | Bucket policy denies non-HTTPS requests |
| Server-side encryption | AES-256 (SSE-S3) on all objects |
| Access logging | Enabled — logs to dedicated bucket |
| 90-day lifecycle | Objects auto-expire — data is transient by design |
| 30-day noncurrent version expiry | Old versions cleaned up automatically |
| IAM scoping | Only specific Lambda roles can access the bucket |

### Review Trigger
- Re-evaluate if CloudFormation/SAM adds native support for MFA Delete.
- Re-evaluate if this solution is adapted for production use with long-lived sensitive data.

## Alternatives Considered

### Option 1: Enable MFA Delete via post-deployment script
- **Effort:** High
- **Why rejected:** Requires root account credentials in an automation pipeline, which
  is a security anti-pattern. The operational complexity outweighs the benefit for a
  sample project.

### Option 2: Document as a manual post-deployment step
- **Effort:** Low
- **Why rejected:** Adds friction to the deployment process for a sample project.
  Users who need MFA Delete for production use can enable it manually. The security
  hardening guide can reference this as an optional step.

## References

- [AWS S3 — Using MFA Delete](https://docs.aws.amazon.com/AmazonS3/latest/userguide/MultiFactorAuthenticationDelete.html)
- [CloudFormation S3 Bucket VersioningConfiguration](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-s3-bucket-versioningconfiguration.html)
- [Security Design Document](../toll-free-registration-automation-security-design.md)
