<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# ADR-002: False Positive — "AWS End User Messaging SMS" Service Name

**Status:** Accepted
**Date:** 2026-04-29
**Deciders:** Project team
**Finding Severity:** High (scanner classification)
**Source:** Holmes security scan

## Context

Holmes security scan flagged "AWS End User Messaging SMS" as not matching the official
AWS service registry. The scanner's service name database did not recognize this name
and flagged references in the documentation and frontend HTML files as potentially
fictitious or incorrect.

## Decision

No change required. This is a false positive. "AWS End User Messaging SMS" is the
official name of the AWS service formerly known as "Amazon Pinpoint SMS and Voice v2".
The service was rebranded in 2024.

**Evidence:**

| Source | Name Used |
|--------|-----------|
| [AWS End User Messaging product page](https://aws.amazon.com/end-user-messaging/) | "AWS End User Messaging" |
| [AWS End User Messaging SMS User Guide](https://docs.aws.amazon.com/sms-voice/latest/userguide/) | "AWS End User Messaging SMS" |
| [Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsendusermessagingsmsandvoicev2.html) | "AWS End User Messaging SMS and Voice V2" |
| AWS CLI namespace | `pinpoint-sms-voice-v2` (legacy naming, not yet renamed) |
| SDK service ID | `Pinpoint SMS Voice V2` (legacy naming) |

The CLI namespace and SDK service ID retain the legacy "pinpoint" naming for backwards
compatibility, but the official service name in all AWS documentation and marketing
materials is "AWS End User Messaging SMS".

## Consequences

### Positive
- This ADR documents the false positive for future scan reviewers, preventing repeated investigation of the same finding.

### Negative
- None. The service name is correct per current AWS documentation and branding.

### Neutral
- The scanner's service name registry has not been updated to include this rebranded service. This is a known gap in the scanning tool.

### Review Trigger
- Remove this ADR if the scanning tool updates its service registry to include "AWS End User Messaging SMS".

## Alternatives Considered

### Option 1: Use the old name "Amazon Pinpoint SMS"
- **Effort:** Low
- **Why rejected:** The old name is deprecated. Using it would be incorrect per current AWS branding guidelines and could confuse users looking for the service in the AWS console (which uses the new name).

### Option 2: Use the CLI namespace name "pinpoint-sms-voice-v2"
- **Effort:** Low
- **Why rejected:** The CLI namespace is a technical identifier, not the service name. Using it in documentation and UI would be confusing to non-technical users.

## References

- [AWS End User Messaging product page](https://aws.amazon.com/end-user-messaging/)
- [AWS End User Messaging SMS User Guide](https://docs.aws.amazon.com/sms-voice/latest/userguide/)
- [Service Authorization Reference — End User Messaging SMS V2](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsendusermessagingsmsandvoicev2.html)
- [AWS CLI Reference — pinpoint-sms-voice-v2](https://docs.aws.amazon.com/cli/latest/reference/pinpoint-sms-voice-v2/)
