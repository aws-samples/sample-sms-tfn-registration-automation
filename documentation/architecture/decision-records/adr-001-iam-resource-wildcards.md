<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# ADR-001: AWS End User Messaging SMS Actions Are Scoped by Resource Type; Step Functions Callbacks Are Not

**Status:** Accepted
**Date:** 2026-08-12 (supersedes the 2026-04-29 version)
**Deciders:** Project team
**Finding Severity:** High (scanner classification)
**Source:** Holmes security scan

**Shared Responsibility Context:** Under the [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/), AWS is responsible for the security of the IAM service infrastructure. Configuring IAM policies with appropriate scope is the customer's responsibility.

## Context

The original version of this record claimed that AWS End User Messaging SMS
registration actions do not support resource-level permissions, and accepted
`Resource: '*'` on that basis. A later scan disputed the claim, so it was checked
against the End User Messaging SMS user guide section "AWS End User Messaging SMS
policy actions". The claim was wrong. Every action this solution calls lists at
least one resource ARN:

| Action | Resource ARN per the user guide |
|--------|--------------------------------|
| `sms-voice:CreateRegistration` | `registration/registrationId` |
| `sms-voice:PutRegistrationFieldValue` | `registration/registrationId` |
| `sms-voice:SubmitRegistrationVersion` | `registration/registrationId` |
| `sms-voice:CreateRegistrationAssociation` | `registration/registrationId`, `phone-number/phoneNumberId` |
| `sms-voice:RequestPhoneNumber` | `phone-number/phoneNumberId`, `pool/poolId` |
| `sms-voice:CreateRegistrationAttachment` | `registration-attachment/registrationAttachmentId` |
| `sms-voice:DescribeRegistrationAttachments` | `registration-attachment/registrationAttachmentId` |
| `sms-voice:TagResource` | `configuration-set`, `opt-out-list`, `phone-number`, `pool`, `sender-id` |
| `sms-voice:DescribeRegistrationVersions` | `registration/registrationId` |
| `sms-voice:DescribeRegistrationFieldValues` | `registration/registrationId` |

The registration and phone number IDs genuinely are unknown at deploy time,
since this function is what creates them. That constrains the resource segment
to a wildcard, but it does not justify a bare `Resource: '*'`: the partition,
region, account, and resource type can all be pinned.

## Decision

Scope every `sms-voice` statement to `arn:{partition}:sms-voice:{region}:{account}:{type}/*`,
split into one statement per resource type so each action only reaches the types
it actually operates on. `RegistrationFunction` now carries four statements
rather than one, and `NotificationFunction`'s read actions are pinned to
`registration/*`.

`states:SendTaskSuccess` and `states:SendTaskFailure` keep `Resource: '*'`. These
operate on an opaque task token, not on a resource ARN, and the Step Functions
authorization reference lists no resource type for them. There is nothing to
pin.

## Consequences

### Positive
- The functions can no longer touch sender IDs, opt-out lists, configuration
  sets, protect configurations, or verified destination numbers
- Cross-account and cross-region use of these credentials is denied by the policy
- Each Lambda still has its own role listing specific action names, with no
  `Action: '*'` or `sms-voice:*`

### Negative
- Within this account and region, a compromised `RegistrationFunction` could
  still modify registrations it did not create. Closing that gap requires either
  a per-registration ARN, which does not exist at deploy time, or tag-based
  conditions, which the service supports on `CreateRegistration` but not on
  `PutRegistrationFieldValue` or `SubmitRegistrationVersion`.
- `TagResource` is granted on `registration/*` and `phone-number/*`. The user
  guide does not list `registration` among its resource types, so if a future
  API change enforces that list strictly the registration tag call may need to
  move or be dropped.

### Review Trigger
- Re-evaluate if the service adds tag-based conditions across all registration
  write actions, which would allow pinning by tag instead of by type
- Re-evaluate before deploying into a shared account that holds registrations
  belonging to other workloads

## References

- AWS End User Messaging SMS user guide, "AWS End User Messaging SMS policy actions"
- [AWS Service Authorization Reference — End User Messaging SMS V2](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonpinpointsmsvoicev2.html)
- [AWS End User Messaging SMS identity-based policy examples](https://docs.aws.amazon.com/sms-voice/latest/userguide/security_iam_id-based-policy-examples.html)
- [Security Design Document](../toll-free-registration-automation-security-design.md)
