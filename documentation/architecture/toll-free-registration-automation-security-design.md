<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# Toll-Free Registration Automation — Security Design

## Shared Responsibility Model

This solution operates under the [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/).

**AWS is responsible for:**
- Security of the underlying cloud infrastructure (compute, storage, networking, managed services)
- Physical security of data centers
- Managed service security (Amazon DynamoDB encryption, AWS Lambda execution environment isolation, Amazon API Gateway TLS termination)

**You (the customer) are responsible for:**
- Reviewing and configuring IAM policies appropriate for your environment
- Setting `AllowedOrigin` to your specific domain before production use
- Enabling AWS CloudTrail for API audit logging
- Configuring Amazon CloudWatch alarms for error monitoring
- Granting `execute-api:Invoke` only to the operators who should submit registrations
- Reviewing data handling practices for compliance with your organization's requirements
- Managing access to the AWS account where this solution is deployed
- Performing your own security assessment before production deployment

This sample code is provided as-is for demonstration purposes. You are responsible
for making your own independent assessment and implementing appropriate security
controls for your use case.

## Architecture Overview

The Toll-Free Registration Automation solution orchestrates the full lifecycle of
toll-free number registration through AWS End User Messaging SMS. The architecture
uses an event-driven, serverless design with the following security boundaries:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Public Boundary                                                             │
│   Browser (static HTML wizard)                                              │
│     │                                                                       │
│     ├── HTTPS ──> Amazon API Gateway (CORS, TLS termination)                │
│     └── HTTPS ──> Amazon S3 (presigned URL, time-limited)                   │
└─────────────────────────────────────────────────────────────────────────────┘
         │                              │
         v                              v
┌─────────────────────────────────────────────────────────────────────────────┐
│ AWS Account Boundary (IAM-controlled)                                       │
│                                                                             │
│   API Gateway ──> Lambda Functions (per-function IAM roles)                 │
│                     │                                                       │
│                     ├──> Amazon DynamoDB (SSE-KMS, PITR)                        │
│                     ├──> Amazon S3 (AES-256, TLS enforced, versioned)       │
│                     ├──> AWS Step Functions (Standard Workflow)              │
│                     ├──> AWS End User Messaging SMS API                     │
│                     └──> Amazon SNS (notifications)                         │
│                                                                             │
│   Amazon EventBridge ──> Event Router Lambda ──> Step Functions callback    │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Security boundaries:**
1. **Public boundary:** Browser communicates only via HTTPS to API Gateway and S3 presigned URLs.
2. **API Gateway boundary:** CORS restricts allowed origins. TLS terminates here. IAM authorization on every route, so callers must send SigV4-signed requests.
3. **Lambda execution boundary:** Each function runs in its own isolated execution environment with a dedicated IAM role scoped to its required actions.
4. **Data store boundary:** DynamoDB and S3 encrypt data at rest. S3 bucket policies enforce TLS. DynamoDB has point-in-time recovery enabled.

## Data Classification

| Data Type | Classification | Storage | Encryption |
|-----------|---------------|---------|------------|
| Company name, address | Business-sensitive | Amazon DynamoDB | AWS managed encryption at rest |
| Tax ID (EIN) | Sensitive PII | Amazon DynamoDB | AWS managed encryption at rest |
| Contact email, phone | PII | Amazon DynamoDB | AWS managed encryption at rest |
| Opt-in screenshots, T&C, privacy policy | Business documents | Amazon S3 | AES-256 server-side encryption |
| Phone numbers (E.164) | PII | Amazon DynamoDB | AWS managed encryption at rest |
| AWS Step Functions task tokens | System internal | Amazon DynamoDB | AWS managed encryption at rest |
| Registration IDs, phone number IDs | System internal | Amazon DynamoDB | AWS managed encryption at rest |
| Amazon SNS notification content | Business-sensitive | In transit only | TLS in transit |

### PII Inventory

This solution handles the following personally identifiable information (PII):

- **Tax IDs (EIN):** Collected in the registration form, stored in DynamoDB, passed to the AWS End User Messaging SMS API for toll-free registration.
- **Email addresses:** Contact email for the registrant, stored in DynamoDB.
- **Phone numbers:** Toll-free numbers provisioned by the workflow and contact phone numbers from the form, stored in DynamoDB.
- **Physical addresses:** Business address for the registrant, stored in DynamoDB.
- **Contact names:** First and last name of the registrant contact, stored in DynamoDB.

## Data Handling Procedures

### Data Retention

| Data Store | Retention | Mechanism |
|------------|-----------|-----------|
| Amazon S3 (upload bucket) | 90 days | S3 lifecycle rule (`ExpirationInDays: 90`) auto-deletes objects |
| Amazon S3 (old versions) | 30 days | S3 lifecycle rule (`NoncurrentVersionExpiration: 30`) |
| Amazon S3 (access logs) | 365 days | S3 lifecycle rule on the logging bucket |
| Amazon DynamoDB | Indefinite | Point-in-time recovery (PITR) enabled for 35-day recovery window |
| Amazon CloudWatch Logs | Default | Lambda log groups use the CloudWatch default retention (no automatic expiration). Configure a retention policy. |

### Data Flow

```
Browser --> (HTTPS) --> Amazon API Gateway --> (IAM role) --> AWS Lambda --> (IAM role) --> Amazon DynamoDB
                                                                        --> (IAM role) --> Amazon S3 (presigned URL)
                                                                        --> (IAM role) --> AWS Step Functions
                                                                        --> (IAM role) --> AWS End User Messaging SMS API
                                                                        --> (IAM role) --> Amazon SNS

Amazon EventBridge --> (IAM role) --> Event Router Lambda --> (IAM role) --> Amazon DynamoDB
                                                          --> (IAM role) --> AWS Step Functions
```

All data in transit uses TLS. No data flows over unencrypted channels.

## Encryption Strategy

### At Rest

- **Amazon DynamoDB:** SSE-KMS with a customer managed key created by the stack (`SSESpecification.SSEType: KMS`, `KMSMasterKeyId` pointing at `RegistrationsTableKey`). Automatic annual key rotation is enabled. Point-in-time recovery is enabled for data durability.
- **Amazon S3 (upload bucket):** AES-256 server-side encryption (SSE-S3) configured via `BucketEncryption` in the SAM template.
- **Amazon S3 (access logs bucket):** AES-256 server-side encryption (SSE-S3).
- **Amazon SNS:** SSE-KMS using the AWS managed key `alias/aws/sns`.

### In Transit

- **Amazon API Gateway:** HTTPS only (TLS 1.2+). HTTP API does not support unencrypted HTTP.
- **Amazon S3 presigned URLs:** HTTPS only. Bucket policy explicitly denies `s3:*` when `aws:SecureTransport` is `false`.
- **AWS Lambda to AWS services:** All AWS SDK calls use HTTPS by default.
- **Amazon SNS notifications:** Email delivery uses TLS where the recipient's mail server supports it.

### Key Management Strategy

This solution uses a mix of customer managed and AWS managed keys:

- **Amazon DynamoDB:** a customer managed KMS key (`RegistrationsTableKey`) created by the stack, with automatic annual rotation and the alias `alias/{StackName}-registrations`. The registrations table holds the most sensitive data in the solution (company tax identifiers, contact details, message samples), so it gets a key you control and can audit through AWS CloudTrail. Each Lambda function that reads or writes the table is granted `kms:Decrypt` and, where it writes, `kms:GenerateDataKey` on that key alone.
- **Amazon SNS:** the AWS managed key `alias/aws/sns`. Notification payloads carry registration status and rejection reasons, not the form data itself.
- **Amazon S3:** SSE-S3 (AES-256). Uploaded opt-in screenshots are transient, expire after 90 days by lifecycle rule, and are never public.

**If your use case involves regulated data** (HIPAA, PCI-DSS, etc.), extend the same pattern to Amazon S3: replace `BucketEncryption` with SSE-KMS and point it at a customer managed key. Consider a dedicated key per data store rather than sharing one key across services, and add a key policy that restricts use to the specific Lambda execution roles.

## IAM Design

### Principle: Per-Function Roles with Least Privilege

Each Lambda function has its own IAM execution role. SAM policy templates scope
DynamoDB, S3, SNS, and Step Functions actions to specific resource ARNs. AWS End
User Messaging SMS actions are scoped by partition, region, account, and resource
type, with a wildcard only on the resource ID, which does not exist until this
solution creates it. The Step Functions callback actions are the one remaining
`Resource: '*'`, because they act on a task token rather than a resource
(see [ADR-001](decision-records/adr-001-iam-resource-wildcards.md)).

| Function | DynamoDB | S3 | EUM SMS | Step Functions | SNS |
|----------|----------|----|---------|----------------|-----|
| IntakeFunction | Read/Write | — | — | StartExecution | — |
| PresignedUrlFunction | — | PutObject | — | — | — |
| RegistrationFunction | Read/Write | Read | RequestPhoneNumber, CreateRegistration, CreateRegistrationAssociation, PutRegistrationFieldValue, CreateRegistrationAttachment, SubmitRegistrationVersion, TagResource, DescribeRegistrationAttachments | — | — |
| EventRouterFunction | Read/Write | — | — | SendTaskSuccess, SendTaskFailure | — |
| NotificationFunction | Read | — | DescribeRegistrationVersions, DescribeRegistrationFieldValues | — | Publish |
| ResumeFunction | Read/Write | — | — | SendTaskSuccess | — |

### Resource Scoping

- **Amazon DynamoDB:** Scoped via `DynamoDBCrudPolicy` / `DynamoDBReadPolicy` SAM templates to the specific table.
- **Amazon S3:** Scoped via `S3CrudPolicy` / `S3ReadPolicy` SAM templates to the specific bucket.
- **Amazon SNS:** Scoped via `SNSPublishMessagePolicy` SAM template to the specific topic.
- **AWS Step Functions:** Scoped via `StepFunctionsExecutionPolicy` SAM template to the specific state machine.
- **AWS End User Messaging SMS:** scoped per resource type to `arn:{partition}:sms-voice:{region}:{account}:{type}/*`, one statement per type. `RegistrationFunction` reaches `registration/*`, `phone-number/*`, `pool/*`, and `registration-attachment/*`; `NotificationFunction` reaches `registration/*` only. The resource ID is a wildcard because the registration and phone number do not exist at deploy time. See [ADR-001](decision-records/adr-001-iam-resource-wildcards.md).
- **Step Functions callback actions** (`SendTaskSuccess`, `SendTaskFailure`): `Resource: '*'`. These take a task token, not a resource ARN, and the Step Functions authorization reference lists no resource type for them.

### No Action Wildcards

Every IAM policy lists specific action names. No policy uses `Action: '*'` or
`Action: 'sms-voice:*'`. Combined with the resource-type scoping above, each
function reaches only the API operations it needs, on only the resource types it
touches.

## API Security

### Amazon API Gateway

- **Protocol:** HTTPS only (HTTP API — TLS 1.2+).
- **Authentication:** IAM authorization (`AWS_IAM`) on every route. Callers need `execute-api:Invoke`. To call the API from a browser, switch to an Amazon Cognito JWT authorizer. See the [Security Hardening Guide](../toll-free-registration-automation-security-hardening.md).
- **CORS:** Configurable via the `AllowedOrigin` SAM parameter (required, no default). Wildcards are rejected by parameter validation. Set this to your specific domain.
- **Input validation:** Lambda functions validate request bodies and reject malformed input with structured error responses.

### Presigned URL Security

- **Time limit:** Presigned URLs expire after a short time window (configurable, recommended 10 minutes).
- **Content type validation:** The presigned URL is generated with a specific content type condition. Only PNG, JPEG, and PDF files are accepted.
- **Size limit:** Maximum file size of 500 KB enforced at the application level.
- **Path traversal prevention:** S3 keys are constructed server-side using the `requestId` as a prefix. User-supplied filenames are sanitized — path separators and directory traversal sequences (`../`) are stripped before constructing the S3 key.
- **Single-use by design:** Each presigned URL targets a specific S3 key. The URL cannot be reused to upload to a different key.

## Error Handling Strategy

This solution uses two distinct error handling patterns based on the invocation context:

### API Lambda Functions (IntakeFunction, PresignedUrlFunction, ResumeFunction)

API-facing Lambda functions return structured JSON error responses to the caller:

```json
{
  "statusCode": 400,
  "body": "{\"error\": \"Validation failed\", \"details\": \"Missing required field: companyName\"}"
}
```

These functions use try/except blocks to catch exceptions and return appropriate
HTTP status codes (400 for validation errors, 500 for internal errors). Error
details are logged to CloudWatch but sensitive information is not returned to the
caller.

### Step Functions Lambda Functions (RegistrationFunction, NotificationFunction)

Lambda functions invoked by Step Functions intentionally let exceptions propagate
as unhandled errors. This is by design:

1. An unhandled exception becomes a `States.TaskFailed` error in Step Functions.
2. The state machine definition includes `Catch` blocks that route failures to the rejection/notification path.
3. Wrapping these calls in try/except would swallow the error and prevent the state machine's error routing from working correctly.

See [ADR-004](decision-records/adr-004-registration-lambda-error-handling.md) for the full rationale.

### Event Router Lambda (EventRouterFunction)

The Event Router uses a hybrid approach: it catches expected conditions (missing
task token, already-completed workflow) and logs them, but lets unexpected errors
propagate. EventBridge automatically retries failed Lambda invocations.

## Logging and Monitoring

### What This Solution Provides

| Service | Logging | Details |
|---------|---------|---------|
| AWS Lambda | CloudWatch Logs | Automatic — each function logs to its own log group |
| AWS Step Functions | Execution history | Built-in — visible in the Step Functions console |
| Amazon S3 | Server access logs | Enabled — logs to a dedicated access logs bucket |
| Amazon API Gateway | — | Not enabled by default. You must enable access logging. |
| Amazon DynamoDB | — | Not enabled by default. Requires CloudTrail data events. |

### What You Must Configure

| Priority | Action | Why |
|----------|--------|-----|
| 1 | Enable AWS CloudTrail | Audit trail for all API calls across all services |
| 2 | Configure CloudWatch alarms | Alert on Lambda errors, Step Functions failures, DynamoDB throttling |
| 3 | Set CloudWatch Logs retention | Lambda log groups default to indefinite retention. Set a retention policy. |
| 4 | Enable API Gateway access logging | Track API request patterns and errors |
| 5 | Consider AWS X-Ray tracing | End-to-end request tracing for debugging |

See the [Security Hardening Guide](../toll-free-registration-automation-security-hardening.md) for step-by-step instructions.

## AWS Service Security Guidelines

### AWS Lambda

- **Runtime:** Python 3.12 (latest supported runtime at time of writing).
- **Execution role:** Per-function IAM roles with least-privilege policies.
- **Environment variables:** Used for resource references (table names, bucket names, topic ARNs, state machine ARN). No secrets are stored in environment variables.
- **Timeout:** 30 seconds default, 120 seconds for RegistrationFunction (multi-step API calls).
- **Memory:** 256 MB — sufficient for API call orchestration workloads.
- **VPC:** Not configured. Lambda functions access only AWS service APIs (no private resources).
- **Reserved concurrency:** Not configured. Consider setting reserved concurrency for production to prevent runaway invocations.

### Amazon DynamoDB

- **Encryption:** SSE-KMS with the stack's customer managed key (`RegistrationsTableKey`), annual rotation enabled.
- **Point-in-time recovery:** Enabled for 35-day recovery window.
- **Billing mode:** PAY_PER_REQUEST (on-demand) — no capacity planning required, auto-scales.
- **Access:** IAM-only. No public access. Each Lambda function's role is scoped to the specific table.
- **GSI:** `registration-id-index` for looking up registrations by AWS-assigned registration ID (used by Event Router for callback correlation).

### Amazon S3

- **Block Public Access:** All four settings enabled on both buckets.
- **Encryption:** AES-256 (SSE-S3) on both buckets.
- **TLS enforcement:** Bucket policy denies all actions when `aws:SecureTransport` is `false`.
- **Versioning:** Enabled on the upload bucket.
- **Access logging:** Upload bucket logs to a dedicated access logs bucket.
- **Lifecycle:** Upload bucket objects expire after 90 days. Old versions expire after 30 days. Access logs expire after 365 days.
- **CORS:** Configurable via `AllowedOrigin` parameter. Only `PUT` method is allowed (for presigned URL uploads).
- **MFA Delete:** Not enabled. See [ADR-003](decision-records/adr-003-s3-mfa-delete.md).

### Amazon API Gateway

- **Type:** HTTP API (lower latency, lower cost than REST API).
- **Protocol:** HTTPS only.
- **CORS:** Configured via SAM parameter. Allows `POST` and `OPTIONS` methods.
- **Authentication:** IAM authorization on every route.
- **Throttling:** Default API Gateway throttling applies. Consider adding usage plans for production.
- **WAF:** Not configured. Consider adding AWS WAF for rate limiting and IP filtering in production.

### AWS Step Functions

- **Type:** Standard Workflow (supports long-running executions for multi-week registration approval).
- **Execution logging:** Built-in execution history in the Step Functions console.
- **IAM:** State machine role is scoped to invoke only the RegistrationFunction and NotificationFunction via `LambdaInvokePolicy` SAM templates.
- **Task tokens:** Used for `waitForTaskToken` integration pattern. Tokens are stored in DynamoDB and used by the Event Router to resume workflows on EventBridge callbacks.
- **Error handling:** `Catch` blocks route failures to the rejection/notification path. `Retry` blocks can be added for transient errors.

### Amazon EventBridge

- **Bus:** Default event bus.
- **Rule:** Captures `Registration Status Change` events from the `aws.sms-voice` source.
- **Target:** Event Router Lambda function.
- **Permission:** Lambda resource-based policy allows EventBridge to invoke the function, scoped to the specific rule ARN.
- **Retry:** EventBridge automatically retries failed Lambda invocations with exponential backoff.

### Amazon SNS

- **Topic:** Single notification topic for all registration status alerts.
- **Subscription:** Email subscription configured via the `NotificationEmail` SAM parameter.
- **Encryption:** SSE-KMS using the AWS managed key `alias/aws/sns`. Switch to a customer managed key if you need CloudTrail visibility into key usage or cross-account access control.
- **Access:** Lambda functions publish via IAM role scoped to the specific topic ARN using `SNSPublishMessagePolicy`.

## References

- [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/)
- [AWS End User Messaging SMS User Guide](https://docs.aws.amazon.com/sms-voice/latest/userguide/)
- [AWS Service Authorization Reference — End User Messaging SMS V2](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsendusermessagingsmsandvoicev2.html)
- [Security Hardening Guide](../toll-free-registration-automation-security-hardening.md)
- [ADR-001: IAM Resource Wildcards](decision-records/adr-001-iam-resource-wildcards.md)
- [ADR-003: S3 MFA Delete](decision-records/adr-003-s3-mfa-delete.md)
- [ADR-004: Registration Lambda Error Handling](decision-records/adr-004-registration-lambda-error-handling.md)
- [ADR-007: Access Logging Scope](decision-records/adr-007-access-logging-scope.md)
- [ADR-008: Access Logs Bucket Self-Logging](decision-records/adr-008-logs-bucket-self-logging.md)
- [ADR-009: Encryption Key Selection](decision-records/adr-009-encryption-key-selection.md)
- [ADR-010: CSP Without 'unsafe-inline'](decision-records/adr-010-csp-without-unsafe-inline.md)
- [ADR-011: Reserved Example Phone Numbers](decision-records/adr-011-reserved-example-phone-numbers.md)
