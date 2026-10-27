<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# ADR-004: Registration Lambda Error Handling — Exceptions Propagate by Design

**Status:** Accepted
**Date:** 2026-04-29
**Deciders:** Project team
**Finding Severity:** Medium
**Source:** Holmes security scan

## Context

Holmes security scan flagged missing try/except blocks in the Registration Lambda
function for AWS End User Messaging SMS API calls (`RequestPhoneNumber`,
`CreateRegistration`, `PutRegistrationFieldValue`, `SubmitRegistrationVersion`, etc.).

The scanner expected all external API calls to be wrapped in exception handlers to
prevent unhandled errors.

## Decision

By design — the Registration Lambda intentionally lets exceptions propagate as
unhandled errors. This is the correct pattern for Lambda functions invoked by
AWS Step Functions.

**How it works:**

1. AWS Step Functions invokes the Registration Lambda as a `Task` state.
2. If the Lambda raises an unhandled exception, Step Functions receives it as a
   `States.TaskFailed` error.
3. The state machine definition includes `Catch` blocks on the registration task
   states that route `States.TaskFailed` errors to the rejection/notification path.
4. The Notification Lambda sends an SNS alert with the error details.
5. The workflow enters a `waitForTaskToken` state for human intervention.

**Why try/except would be wrong:**

```python
# ❌ WRONG — swallows the error, Step Functions thinks the task succeeded
try:
    client.submit_registration_version(RegistrationId=reg_id)
except Exception as e:
    logger.error(f"Registration failed: {e}")
    return {"status": "error", "message": str(e)}  # Step Functions sees this as SUCCESS

# ✅ CORRECT — exception propagates, Step Functions catches it via Catch block
client.submit_registration_version(RegistrationId=reg_id)
# If this throws, Lambda returns an error, Step Functions routes to Catch block
```

Wrapping API calls in try/except and returning an error response would cause Step
Functions to treat the invocation as successful (because the Lambda returned a 200
response). The state machine's `Catch` blocks would not fire, and the
rejection/notification path would be bypassed.

## Consequences

### Positive
- Step Functions `Catch` blocks work correctly — errors are routed to the rejection/notification path.
- Error details (exception type, message) are preserved in the Step Functions execution history for debugging.
- The operator receives an SNS notification with the failure reason.
- The workflow pauses for human intervention rather than silently failing.

### Negative
- Lambda CloudWatch Logs show unhandled exceptions, which may trigger alerts if CloudWatch alarms are configured on Lambda error metrics. This is expected behavior — the alarm correctly indicates that a registration step failed.

### Neutral
- API-facing Lambda functions (IntakeFunction, PresignedUrlFunction, ResumeFunction) DO use try/except blocks because they return HTTP responses directly to the caller. The error handling pattern differs by invocation context.

### Review Trigger
- Re-evaluate if Step Functions adds native support for distinguishing between "Lambda returned an error response" and "Lambda threw an exception".

## Error Handling Pattern Summary

| Function | Invoked By | Error Pattern | Reason |
|----------|-----------|---------------|--------|
| IntakeFunction | API Gateway | try/except → structured HTTP error | Caller needs HTTP status codes |
| PresignedUrlFunction | API Gateway | try/except → structured HTTP error | Caller needs HTTP status codes |
| ResumeFunction | API Gateway | try/except → structured HTTP error | Caller needs HTTP status codes |
| RegistrationFunction | Step Functions | Let exceptions propagate | Step Functions Catch blocks handle routing |
| NotificationFunction | Step Functions | Let exceptions propagate | Step Functions Catch blocks handle routing |
| EventRouterFunction | EventBridge | Hybrid — catch expected, propagate unexpected | EventBridge retries on failure |

## References

- [AWS Step Functions — Error Handling](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)
- [AWS Step Functions — Task State](https://docs.aws.amazon.com/step-functions/latest/dg/amazon-states-language-task-state.html)
- [AWS Lambda — Error Handling with Step Functions](https://docs.aws.amazon.com/lambda/latest/dg/invocation-retries.html)
- [Security Design Document](../toll-free-registration-automation-security-design.md)
