<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# Toll-Free Registration Automation

Automated toll-free number registration pipeline using AWS Step Functions,
Amazon EventBridge, AWS Lambda, Amazon DynamoDB, Amazon Simple Storage Service (Amazon S3),
and Amazon Simple Notification Service (Amazon SNS). Handles the
full lifecycle - phone number provisioning, registration creation, field
population, submission, and approval tracking - with event-driven callbacks
and human-in-the-loop for rejections.

> **Important:** This sample code is provided as-is for demonstration and
> educational purposes. You are responsible for making your own independent
> assessment and implementing appropriate security controls for your use case.
> See the [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/).

> **Cost Warning:** Deploying this solution creates billable AWS resources.
> Toll-free number lease fees apply immediately upon provisioning.
> See [AWS End User Messaging Pricing](https://aws.amazon.com/end-user-messaging/pricing/)
> and the [Cleanup](#cleanup) section.

## Architecture

![Toll-Free Registration Automation Architecture](documentation/architecture/toll-free%20automation%20architecture.png)

```
CLI/SDK (SigV4) --> Amazon API Gateway --> Intake Lambda --> DynamoDB
                                         --> Step Functions
                                               |
                                               v
                                         1. Request Phone Number (TOLL_FREE)
                                         2. Create Registration
                                         3. Associate Phone with Registration
                                         4. Populate Fields
                                         5. Submit Registration
                                         6. Wait for Approval <-- EventBridge callback
                                               |
                                          (on rejection)
                                               |
                                         7. Notify Operator --> SNS
                                         8. Wait for Human Fix
                                         9. Resume
                                               |
                                          (on approval)
                                               |
                                        10. Notify Complete --> SNS
```

## How It Works

### Registration Flow

1. Collect the registration details. The registration wizard (static HTML front end) validates them and generates the equivalent AWS CLI commands. It runs locally and does not call the API.
2. Upload opt-in screenshots directly to Amazon S3 with presigned URLs from `POST /api/upload-url`
3. Send the registration to `POST /api/submit` with a SigV4-signed request (AWS CLI, SDK or `curl --aws-sigv4`). Intake Lambda writes to Amazon DynamoDB and starts an AWS Step Functions execution
4. Step Functions orchestrates the registration process:

| Step | Action | Wait? |
|------|--------|-------|
| 1 | Request a toll-free phone number | No |
| 2 | Create registration, associate phone number, populate all fields, submit | No |
| 3 | Wait for carrier approval | Yes - `waitForTaskToken` (1-2 weeks) |
| 4 | Send completion notification | No |

5. Amazon EventBridge captures `Registration Status Change` events from AWS End User Messaging SMS
6. Event Router Lambda receives the event, looks up the task token in Amazon DynamoDB, and calls `SendTaskSuccess` or `SendTaskFailure` to resume the workflow
7. On rejection, the workflow notifies the operator via Amazon SNS and pauses for human intervention
8. On approval, sends a success notification
9. If an EUM SMS API call or workflow step fails, or the registration is closed or deleted, the workflow sends a failure notification via Amazon SNS and stops

### Phone Number Timing

Toll-free registrations require `ASSOCIATE_BEFORE_SUBMIT` - the phone number
must be purchased and associated with the registration before submitting for
review. The workflow handles this automatically by requesting the phone number
as the first step.

### Human-in-the-Loop (Rejection Handling)

When a registration is rejected:

1. AWS Step Functions catches the failure and branches to the rejection path
2. Notification Lambda sends an Amazon SNS alert with the rejection reason
3. The workflow enters a `waitForTaskToken` state, pausing indefinitely
4. The operator fixes the registration in the AWS console and resubmits
5. Amazon EventBridge fires again when the status changes, automatically resuming the workflow
6. Alternatively, the operator calls `POST /api/resume/{requestId}` to manually resume

## Project Structure

```
sample-sms-tfn-registration-automation/
├── frontend/
│   ├── toll-free-registration-wizard.html    # Static form (CLI command generator)
│   ├── wizard.css                            # Wizard styles
│   └── wizard.js                             # Wizard logic and event wiring
├── lambda/
│   ├── intake/app.py                         # API --> DynamoDB --> Start Step Functions
│   ├── presigned_url/app.py                  # S3 presigned URL generator
│   ├── registration/app.py                   # Create reg, request phone, associate, populate, submit
│   ├── event_router/app.py                   # EventBridge --> task token --> SFN callback
│   ├── notification/app.py                   # SNS alerts for status changes
│   ├── resume/app.py                         # Human-in-the-loop resume endpoint
│   └── shared/
│       └── dry_run.py                        # Dry run helpers for testing
├── statemachine/
│   └── registration_workflow.asl.json        # Step Functions definition
├── documentation/
│   ├── architecture/
│   │   └── decision-records/
│   └── toll-free-registration-automation-user-guide.md
├── tests/
│   ├── unit/
│   ├── integration/
│   └── events/
├── template.yaml                             # SAM template (all infrastructure)
├── samconfig.toml
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
└── SECURITY.md
```

## Lambda Functions

| Function | Trigger | Purpose |
|----------|---------|---------|
| IntakeFunction | POST /api/submit | Validates input, writes to Amazon DynamoDB, starts workflow |
| PresignedUrlFunction | POST /api/upload-url | Generates time-limited S3 PUT URLs |
| RegistrationFunction | Step Functions | Requests phone, creates registration, associates, populates fields, submits |
| EventRouterFunction | EventBridge | Receives status change events, resumes workflow via task tokens |
| NotificationFunction | Step Functions | Sends Amazon SNS alerts with rejection details |
| ResumeFunction | POST /api/resume/{id} | Human-in-the-loop resume endpoint |

## DynamoDB Schema

### Table: `{StackName}-registrations`

| Attribute | Type | Description |
|-----------|------|-------------|
| `requestId` (PK) | String | Unique registration request ID (UUID) |
| `status` | String | Current workflow state |
| `companyFields` | Map | Company information form data |
| `contactFields` | Map | Contact information form data |
| `useCaseFields` | Map | Messaging use case form data |
| `messageSamples` | Map | Sample messages |
| `attachments` | Map | S3 keys for uploaded files |
| `phoneConfig` | Map | Phone number configuration |
| `registrationId` | String | AWS End User Messaging SMS registration ID |
| `phoneNumberId` | String | Phone number ID |
| `phoneNumber` | String | E.164 phone number |
| `taskTokens` | Map | Step Functions task tokens |
| `createdAt` | String | ISO 8601 timestamp |
| `updatedAt` | String | ISO 8601 timestamp |

## API Endpoints

Every route uses IAM authorization. Sign requests with SigV4 using credentials
that allow `execute-api:Invoke`, for example `curl --aws-sigv4` (see the
[User Guide](documentation/toll-free-registration-automation-user-guide.md)).
Unsigned requests receive 403.

### POST /api/submit
Submit a registration request. Starts the automated workflow.

### POST /api/upload-url
Generate a presigned S3 URL for direct-to-S3 file upload.

### POST /api/resume/{requestId}
Resume a paused workflow after human intervention on a rejected registration.

## Prerequisites

- AWS CLI v2
- AWS Serverless Application Model (AWS SAM) CLI
- Python 3.12+
- AWS account with AWS End User Messaging SMS enabled

## Deployment

```bash
sam build
sam deploy --guided
```

## Dry Run Mode

Test the full workflow without real API calls:

```bash
sam deploy --parameter-overrides "DryRun=true" "NotificationEmail=you@example.com" "AllowedOrigin=*"
```

`--parameter-overrides` replaces the values in `samconfig.toml`, so pass
`NotificationEmail` here as well.

Returns synthetic registration and phone number IDs. Amazon DynamoDB,
AWS Step Functions, and Amazon SNS still run for real.

## Security

This solution follows the [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/).

**AWS is responsible for:** Security of the underlying cloud infrastructure and managed services (AWS Lambda execution isolation, Amazon DynamoDB encryption, Amazon API Gateway TLS termination).

**You are responsible for:** Configuring IAM policies, limiting who has `execute-api:Invoke` on the API, restricting CORS origins, enabling AWS CloudTrail, and performing your own security assessment before production use. These are ongoing responsibilities that require continuous monitoring and periodic review, not one-time setup tasks.

**What this solution provides:** Encryption at rest (Amazon DynamoDB with a customer managed AWS KMS key, Amazon S3 AES-256, Amazon SNS with an AWS managed key), encryption in transit (HTTPS, TLS enforcement), IAM (SigV4) authorization on every API route, per-function IAM roles with least-privilege policies, S3 Block Public Access, versioning, and access logging.

**What you must configure:** Who can invoke the API, CORS origin restriction, CloudTrail, CloudWatch alarms, and CloudWatch Logs retention policies.

See the [Security Design Document](documentation/architecture/toll-free-registration-automation-security-design.md) for the full architecture, data classification, and encryption strategy. See the [Security Hardening Guide](documentation/toll-free-registration-automation-security-hardening.md) for step-by-step production hardening instructions.

## Cleanup

Stop any running Step Functions executions first. AWS CloudFormation cannot
delete the state machine while executions are running, and `sam delete` waits.

```bash
SM_ARN=$(aws cloudformation describe-stacks --stack-name <your-stack-name> --region <your-region> \
  --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" --output text)
for arn in $(aws stepfunctions list-executions --state-machine-arn "$SM_ARN" --status-filter RUNNING \
  --region <your-region> --query 'executions[].executionArn' --output text); do
  aws stepfunctions stop-execution --execution-arn "$arn" --region <your-region>
done

sam delete --stack-name <your-stack-name> --region <your-region>

# Delete the registration and phone number separately:
aws pinpoint-sms-voice-v2 delete-registration --registration-id <REG_ID>
aws pinpoint-sms-voice-v2 release-phone-number --phone-number-id <PHONE_ID>
```

## Additional Resources

- [AWS End User Messaging SMS User Guide - Registrations](https://docs.aws.amazon.com/sms-voice/latest/userguide/registrations.html)
- [AWS End User Messaging Pricing](https://aws.amazon.com/end-user-messaging/pricing/)
- [CLI Reference: pinpoint-sms-voice-v2](https://docs.aws.amazon.com/cli/latest/reference/pinpoint-sms-voice-v2/)

## Reporting Security Issues

See [SECURITY](SECURITY.md) for how to report a
security issue. Please do not create a public GitHub issue for security findings.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
