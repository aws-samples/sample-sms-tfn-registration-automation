<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# ADR-009: Customer Managed KMS Key for DynamoDB, AWS Managed Key for SNS

**Status:** Accepted
**Date:** 2026-08-12
**Deciders:** Project team
**Finding Severity:** High (scanner classification)
**Source:** Holmes security scan

## Context

Holmes raised two High findings on encryption at rest:

1. The SNS notification topic had no encryption configured at all.
2. The DynamoDB registrations table used `SSESpecification.SSEEnabled: true`
   without a key, which resolves to an AWS owned key. The baseline policy
   requires a customer managed key for data stores holding sensitive data.

The registrations table holds the most sensitive data in the solution: company
tax identifiers, support contact details, and message samples. The SNS topic
carries registration status transitions and rejection reasons, not the form data.

## Decision

Match the key type to what the resource actually stores.

**DynamoDB: customer managed key.** The stack creates `RegistrationsTableKey`
with `EnableKeyRotation: true` and the alias
`alias/{StackName}-registrations`. The table sets `SSEType: KMS` and points
`KMSMasterKeyId` at that key. Every Lambda function that touches the table gets
`kms:Decrypt` on that key alone, and the four that write also get
`kms:GenerateDataKey`. The notification function is read-only, so it gets
`kms:Decrypt` only.

**SNS: AWS managed key.** The topic sets `KmsMasterKeyId: alias/aws/sns`. A
customer managed key here would add a key policy to maintain for data that is
already a derived, low-sensitivity signal.

**S3: SSE-S3 (AES-256), unchanged.** Uploaded opt-in screenshots are transient
and expire after 90 days by lifecycle rule.

The key policy grants `kms:*` to the account root, which is the standard base
policy AWS recommends so the key remains manageable through IAM. Access is then
granted per function through the execution role policies rather than in the key
policy itself.

## Consequences

### Positive
- The most sensitive data store is protected by a key you own, rotate, and can
  audit through AWS CloudTrail
- Per-function key grants keep the blast radius of any single role narrow
- Resolves both High findings without a documented exception

### Negative
- One customer managed key costs roughly 1 USD per month plus request charges
- `sam delete` schedules the key for deletion rather than removing it
  immediately, so a redeploy under the same stack name within the waiting period
  will fail on the alias

### If you need more
For regulated data, extend the same pattern to S3 and SNS with dedicated keys
per data store, and tighten the key policy to name the specific Lambda execution
roles instead of relying on IAM policies alone.

## References

- [DynamoDB encryption at rest](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/EncryptionAtRest.html)
- [SNS server-side encryption](https://docs.aws.amazon.com/sns/latest/dg/sns-server-side-encryption.html)
- [KMS key policies](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html)
- [Security Design Document](../toll-free-registration-automation-security-design.md)
