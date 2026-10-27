<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# ADR-007: Access Logging Scope — CloudTrail and API Gateway Logging as Post-Deployment Configuration

**Status:** Accepted
**Date:** 2026-04-29
**Deciders:** Project team
**Finding Severity:** High (scanner classification)
**Source:** Holmes security scan

## Context

Holmes security scan flagged that Amazon DynamoDB access logging (via AWS CloudTrail
data events) and Amazon API Gateway access logging are not enabled by default in the
deployed solution. The scanner expects these to be configured in the SAM template.

## Decision

Access logging for DynamoDB (CloudTrail data events) and API Gateway access logs are
documented as post-deployment configuration steps in the Security Hardening Guide
rather than enabled by default in the SAM template.

Reasons:

1. **CloudTrail data events incur per-event costs.** Enabling CloudTrail data events
   for DynamoDB in a sample project could generate unexpected charges for users who
   deploy it for testing. This is a cost-sensitive decision for a demo/sample solution.
2. **CloudTrail is account-level, not stack-level.** A CloudTrail trail is typically
   configured once per account, not per-application. Including it in the SAM template
   would create a trail that may conflict with existing account-level trails.
3. **API Gateway access logging requires a CloudWatch Logs role ARN.** Configuring
   API Gateway access logging in CloudFormation requires an account-level
   `ApiGateway::Account` resource with a CloudWatch Logs role, which may conflict
   with existing configurations.
4. **The Security Hardening Guide provides step-by-step instructions.** Priority 3
   (CloudTrail) and Priority 4 (CloudWatch alarms) in the hardening guide cover
   these controls with specific commands and verification steps.

## Consequences

### Positive
- No unexpected CloudTrail data event charges for users deploying the sample
- No conflicts with existing account-level CloudTrail or API Gateway configurations
- Clear documentation of how to enable these controls when needed

### Negative
- Access logging is not enabled out of the box
- Users must follow the hardening guide to enable audit logging

### Compensating Controls
- AWS Lambda CloudWatch Logs are enabled automatically for all functions
- AWS Step Functions execution history is built-in
- Amazon S3 server access logging is enabled on the upload bucket
- The Security Hardening Guide documents CloudTrail and API Gateway logging as Priority 3-4 steps

## References

- [Security Hardening Guide](../../toll-free-registration-automation-security-hardening.md)
- [Security Design Document](../toll-free-registration-automation-security-design.md)
- [AWS CloudTrail Pricing](https://aws.amazon.com/cloudtrail/pricing/)
