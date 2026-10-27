<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# ADR-008: Access Logs Bucket Logs to Itself Under a Separate Prefix

**Status:** Accepted
**Date:** 2026-08-12
**Supersedes:** the earlier decision to accept this finding as-is
**Deciders:** Project team
**Finding Severity:** High (scanner classification)
**Source:** Holmes security scan

## Context

Holmes flagged that `UploadAccessLogsBucket` had no access logging of its own,
leaving a gap in the logging chain. The original decision was to accept the
finding, on the grounds that self-logging causes a feedback loop and that a
third bucket was not worth the complexity in a sample.

That reasoning was wrong on the first point. Amazon S3 supports a bucket as its
own log destination provided the log file prefix differs from the prefix the
source bucket writes to. S3 does not generate access log records for the log
delivery writes themselves, so the feedback loop does not occur.

The finding is also classified High under the PCSR baseline policy, which
requires remediation rather than acceptance before public release.

## Decision

Enable server access logging on `UploadAccessLogsBucket` targeting itself, using
a prefix distinct from the one the upload bucket writes to:

- `UploadBucket` logs to `UploadAccessLogsBucket` under `upload-bucket-logs/`
- `UploadAccessLogsBucket` logs to itself under `access-logs-bucket-logs/`

Versioning is enabled on the logs bucket, and the lifecycle configuration
expires current objects after 365 days and noncurrent versions after 30 days,
so log volume stays bounded without manual cleanup.

## Consequences

### Positive
- Complete logging chain: access to the logs themselves is auditable
- No third bucket, so no additional resources to manage or pay for
- Resolves the High finding without a documented exception

### Negative
- Log objects and their own access records share one bucket, so prefix
  discipline matters if you add further log sources
- Versioning on a log bucket increases storage slightly until noncurrent
  versions expire

### Compensating Controls
- Block Public Access enabled on all 4 settings
- AES-256 server-side encryption
- TLS enforcement via bucket policy (DenyInsecureTransport)
- Lifecycle expiration on both current and noncurrent objects
- IAM-only access. No Lambda function has access to the logs bucket.

## References

- [AWS S3 Server Access Logging](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ServerLogs.html)
- [Security Design Document](../toll-free-registration-automation-security-design.md)
