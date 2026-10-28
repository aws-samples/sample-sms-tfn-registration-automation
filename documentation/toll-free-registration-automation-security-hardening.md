<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# Toll-Free Registration Automation — Production Security Hardening Guide

This guide provides step-by-step instructions for hardening this solution
before production use. Complete these steps in priority order.

## Shared Responsibility Model

This solution operates under the [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/).

**AWS is responsible for:** Security of the underlying cloud infrastructure — compute, storage, networking, and managed service internals (Amazon DynamoDB encryption engine, AWS Lambda execution isolation, Amazon API Gateway TLS termination).

**You (the customer) are responsible for:** Configuring the security controls listed in this guide. The steps below represent your security responsibilities when deploying this solution. Each step includes the specific risk, measurable outcome, implementation commands, and verification procedure. Security is an ongoing obligation — these controls require continuous monitoring, periodic review, and updates as your environment evolves.

See the [Security Design Document](architecture/toll-free-registration-automation-security-design.md) for the full security architecture, data classification, and encryption strategy.

## Priority 1: Restrict CORS Origin (Critical)

**Risk:** A wildcard `AllowedOrigin` allows any website to call your API.

**Measurable outcome:** API requests are only accepted from your specific domain,
reducing the attack surface from all origins to one.

```bash
# Update the AllowedOrigin parameter to your domain
sam deploy --parameter-overrides \
  "NotificationEmail=your-email@example.com" \
  "AllowedOrigin=https://yourdomain.com" \
  "DryRun=false"
```

**Verification:**
```bash
# This should succeed (your domain)
curl -H "Origin: https://yourdomain.com" \
  -X OPTIONS https://<api-id>.execute-api.<region>.amazonaws.com/prod/api/submit

# This should be rejected (different domain)
curl -H "Origin: https://evil.com" \
  -X OPTIONS https://<api-id>.execute-api.<region>.amazonaws.com/prod/api/submit
```

## Priority 2: Choose Your API Authentication (High)

**Default:** Every route uses IAM authorization (`EnableIamAuthorizer: true` with
`DefaultAuthorizer: AWS_IAM`).
Callers sign requests with SigV4 using credentials that allow `execute-api:Invoke`.
Unsigned requests receive 403.

**Risk:** Any IAM principal in the account with `execute-api:Invoke` on the API
can submit registrations, and each submission buys a toll-free number.

**Measurable outcome:** Only the operators you choose can submit registrations or
resume workflows.

Scope invoke rights to a dedicated operator role instead of relying on broad
administrator policies:

```json
{
  "Effect": "Allow",
  "Action": "execute-api:Invoke",
  "Resource": "arn:aws:execute-api:<region>:<account-id>:<api-id>/prod/POST/api/*"
}
```

If you build a browser front end that calls the API directly, replace IAM
authorization with an Amazon Cognito JWT authorizer:

```yaml
Api:
  Type: AWS::Serverless::HttpApi
  Properties:
    Auth:
      DefaultAuthorizer: CognitoAuthorizer
      Authorizers:
        CognitoAuthorizer:
          AuthorizationScopes:
            - email
          IdentitySource: $request.header.Authorization
          JwtConfiguration:
            issuer: !Sub "https://cognito-idp.${AWS::Region}.amazonaws.com/<pool-id>"
            audience:
              - <client-id>
```

**Verification:**
```bash
# Unsigned request: should return 403
curl -X POST https://<api-id>.execute-api.<region>.amazonaws.com/prod/api/submit \
  -H "Content-Type: application/json" \
  -d '{}'

# Signed request: should return 400 (validation error on the empty body)
curl -X POST https://<api-id>.execute-api.<region>.amazonaws.com/prod/api/submit \
  --aws-sigv4 "aws:amz:<region>:execute-api" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-security-token: $AWS_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

## Priority 3: Enable AWS CloudTrail (High)

**Risk:** No audit trail of API calls to AWS services used by this solution.

**Measurable outcome:** All management and data events are logged, providing
forensic capability for security investigations.

```bash
# Create an S3 bucket for CloudTrail logs
aws s3api create-bucket \
  --bucket toll-free-reg-auto-cloudtrail-<account-id> \
  --region <region>

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket toll-free-reg-auto-cloudtrail-<account-id> \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# Create the trail
aws cloudtrail create-trail \
  --name toll-free-reg-auto-trail \
  --s3-bucket-name toll-free-reg-auto-cloudtrail-<account-id> \
  --is-multi-region-trail \
  --enable-log-file-validation

# Start logging
aws cloudtrail start-logging --name toll-free-reg-auto-trail

# Enable DynamoDB data events (optional — adds cost per event)
aws cloudtrail put-event-selectors \
  --trail-name toll-free-reg-auto-trail \
  --advanced-event-selectors '[{
    "Name": "DynamoDB data events",
    "FieldSelectors": [
      {"Field": "eventCategory", "Equals": ["Data"]},
      {"Field": "resources.type", "Equals": ["AWS::DynamoDB::Table"]},
      {"Field": "resources.ARN", "StartsWith": ["arn:aws:dynamodb:<region>:<account-id>:table/toll-free-reg-auto-registrations"]}
    ]
  }]'
```

**Verification:**
```bash
# Check trail status
aws cloudtrail get-trail-status --name toll-free-reg-auto-trail

# Look for recent events (after a few minutes)
aws cloudtrail lookup-events --max-results 5
```

## Priority 4: Configure Amazon CloudWatch Alarms (High)

**Risk:** Lambda errors, Step Functions failures, and DynamoDB throttling
go unnoticed without alarms.

**Measurable outcome:** Operators are alerted within 5 minutes of any
Lambda error, Step Functions failure, or DynamoDB throttle event.

```bash
# Alarm for Lambda errors (repeat for each function)
aws cloudwatch put-metric-alarm \
  --alarm-name "toll-free-reg-auto-IntakeFunction-Errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --evaluation-periods 1 \
  --dimensions Name=FunctionName,Value=<IntakeFunction-name> \
  --alarm-actions <sns-topic-arn>

# Alarm for Step Functions failures
aws cloudwatch put-metric-alarm \
  --alarm-name "toll-free-reg-auto-Workflow-Failures" \
  --metric-name ExecutionsFailed \
  --namespace AWS/States \
  --statistic Sum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --evaluation-periods 1 \
  --dimensions Name=StateMachineArn,Value=<state-machine-arn> \
  --alarm-actions <sns-topic-arn>

# Alarm for DynamoDB throttling
aws cloudwatch put-metric-alarm \
  --alarm-name "toll-free-reg-auto-DynamoDB-Throttles" \
  --metric-name ThrottledRequests \
  --namespace AWS/DynamoDB \
  --statistic Sum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --evaluation-periods 1 \
  --dimensions Name=TableName,Value=toll-free-reg-auto-registrations \
  --alarm-actions <sns-topic-arn>
```

**Verification:**
```bash
aws cloudwatch describe-alarms --alarm-name-prefix "toll-free-reg-auto" \
  --query 'MetricAlarms[*].[AlarmName,StateValue]' --output table
```

## Priority 5: Consider AWS WAF (Medium)

**Risk:** No rate limiting or IP filtering on the API Gateway endpoints.

**Measurable outcome:** API requests are rate-limited and known malicious
IPs are blocked before reaching Lambda functions.

```bash
# Create a WAF web ACL with rate limiting
aws wafv2 create-web-acl \
  --name toll-free-reg-auto-waf \
  --scope REGIONAL \
  --default-action '{"Allow":{}}' \
  --rules '[{
    "Name": "RateLimit",
    "Priority": 1,
    "Action": {"Block": {}},
    "Statement": {
      "RateBasedStatement": {
        "Limit": 100,
        "AggregateKeyType": "IP"
      }
    },
    "VisibilityConfig": {
      "SampledRequestsEnabled": true,
      "CloudWatchMetricsEnabled": true,
      "MetricName": "RateLimit"
    }
  }]' \
  --visibility-config '{"SampledRequestsEnabled":true,"CloudWatchMetricsEnabled":true,"MetricName":"WebACL"}'

# Associate with API Gateway (requires the API Gateway stage ARN)
aws wafv2 associate-web-acl \
  --web-acl-arn <web-acl-arn> \
  --resource-arn "arn:aws:apigateway:<region>::/restapis/<api-id>/stages/prod"
```

## Summary

| Priority | Action | Risk Level | Effort |
|----------|--------|------------|--------|
| 1 | Restrict CORS origin | Critical | Low (parameter change) |
| 2 | Scope API invoke rights | High | Low (IAM policy) |
| 3 | Enable CloudTrail | High | Medium (trail + bucket setup) |
| 4 | Configure CloudWatch alarms | High | Medium (alarm per resource) |
| 5 | Add AWS WAF | Medium | Medium (WAF + association) |
