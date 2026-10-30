<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# Automating Toll-Free Registration with AWS End User Messaging SMS

## The Challenge

US toll-free number registration through AWS End User Messaging SMS requires a multi-step process:

1. Request a toll-free phone number
2. Create a `US_TOLL_FREE_REGISTRATION` registration
3. Associate the phone number with the registration **before** submission (`ASSOCIATE_BEFORE_SUBMIT`)
4. Populate all required fields (company info, contact info, messaging use case)
5. Upload supporting documents (opt-in screenshots)
6. Submit the registration for carrier review
7. Wait for approval (can take days to weeks)
8. Handle rejections — fix issues, resubmit, and wait again

Each step depends on the previous one. If a registration is rejected, someone must notice, diagnose the issue, fix it in the console, and resubmit. Without automation, this is a manual, error-prone process.

## The Solution

This solution automates the entire toll-free registration lifecycle using AWS serverless services. You submit a single form and the system handles everything — including waiting for approvals and alerting you when something needs attention.

### How It Works

**You fill out one form.** A web-based wizard collects all the information needed for toll-free registration in a single session — company details, contact information, messaging use case, sample messages, and opt-in documentation.

**The system takes over.** When you submit, the solution:

- Requests a toll-free phone number (`NumberType: TOLL_FREE`)
- Creates a `US_TOLL_FREE_REGISTRATION` and associates the phone number **before** submission
- Populates all required registration fields from your form data
- Uploads any attachments (opt-in screenshots) from S3
- Submits the registration for carrier review
- Waits for approval via real-time EventBridge status change events
- Sends you an email notification when the registration is complete

**If something gets rejected, you get notified immediately.** The system sends an email with the registration ID, rejection reason, denied fields, and instructions for fixing the issue. The workflow pauses and waits for you to make corrections. Once fixed, you can resume via the `/api/resume` endpoint or wait for the EventBridge status change.

### Key Difference from 10DLC

Toll-free registration is simpler than 10DLC — there is only **one registration type** (`US_TOLL_FREE_REGISTRATION`) instead of separate brand, vetting, and campaign registrations. The phone number is associated **before** submission (`ASSOCIATE_BEFORE_SUBMIT`), not after approval. This means the workflow is a linear sequence rather than a branching multi-registration flow.

## Prerequisites

- **AWS Account** with AWS End User Messaging SMS enabled
- **AWS CLI v2** installed and configured
- **AWS SAM CLI** installed (`pip install aws-sam-cli`)
- **Python 3.12** installed
- A valid **email address** for notifications
- Your company's registration details (legal name, tax ID, address)
- An **opt-in workflow description** and screenshot
- Publicly accessible **privacy policy** and **terms and conditions** URLs, required for new toll-free registrations since 15 September 2026
- At least one **sample message** that reflects what you plan to send

## Deployment

### 1. Build the application

```bash
cd sample-sms-tfn-registration-automation
sam build
```

### 2. Deploy (first time — guided)

```bash
sam deploy --guided
```

SAM prompts you for:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `Stack Name` | CloudFormation stack name | `toll-free-reg-auto` |
| `AWS Region` | Deployment region | `us-west-2` (from `samconfig.toml`) |
| `NotificationEmail` | Email for SNS alerts | *(required)* |
| `AllowedOrigin` | CORS origin for the front end | *(required)* |
| `DryRun` | Skip real EUM SMS API calls | `false` |

### 3. Confirm the SNS subscription

Check your email and click the confirmation link from Amazon SNS.

### 4. Subsequent deployments

```bash
sam build && sam deploy
```

## Configuration

### Dry Run Mode

Set `DryRun=true` to test the full workflow without making real EUM SMS API calls or incurring phone number lease fees. In dry run mode:

- Phone number provisioning returns a synthetic toll-free number (`+18005550199`)
- Registration creation returns synthetic registration IDs
- DynamoDB, Step Functions, SNS, and EventBridge all run for real
- You can test the complete end-to-end flow safely

```bash
sam deploy --parameter-overrides "DryRun=true" "NotificationEmail=you@example.com" "AllowedOrigin=http://localhost:3000"
```

### CORS Origin

For production, restrict the CORS origin to your specific domain:

```bash
sam deploy --parameter-overrides "AllowedOrigin=https://yourdomain.com" "NotificationEmail=you@example.com"
```

## Monitoring

### CloudWatch Logs

Each Lambda function writes structured logs to CloudWatch. View logs for a specific function:

```bash
sam logs --stack-name toll-free-reg-auto --name IntakeFunction --tail
sam logs --stack-name toll-free-reg-auto --name RegistrationFunction --tail
sam logs --stack-name toll-free-reg-auto --name EventRouterFunction --tail
```

### DynamoDB Status Checks

Query the registrations table to check the current status of any request:

```bash
aws dynamodb get-item \
  --table-name toll-free-reg-auto-registrations \
  --key '{"requestId": {"S": "YOUR-REQUEST-ID"}}' \
  --query 'Item.{status:status.S,registrationId:registrationId.S,phoneNumber:phoneNumber.S}'
```

### Step Functions Console

View the state machine execution in the AWS Step Functions console to see which state the workflow is currently in and inspect input/output at each step.

## Handling Rejections

When a toll-free registration is rejected (`REQUIRES_UPDATES`), the system:

1. Sends an email notification with the rejection reason and denied fields
2. Pauses the workflow at the `WaitForHumanIntervention` state
3. Waits for you to fix the issue

### To fix and resume:

1. Open the AWS End User Messaging SMS console
2. Find the registration by ID (included in the notification email)
3. Fix the rejected fields
4. Resubmit the registration version in the console
5. **Option A:** Wait for the EventBridge status change event to automatically resume the workflow
6. **Option B:** Call the resume endpoint manually:

```bash
# ApiEndpoint already ends in /prod
ApiEndpoint=$(aws cloudformation describe-stacks --stack-name <stack-name> \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text)

curl -X POST "${ApiEndpoint}/api/resume/<request-id>" \
  --aws-sigv4 "aws:amz:<region>:execute-api" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-security-token: $AWS_SESSION_TOKEN"
```

The API uses IAM authorization, so the request must be signed with credentials
that allow `execute-api:Invoke`. `--aws-sigv4` needs curl 7.75 or later. Drop the
`x-amz-security-token` header if you use long-term credentials.

## Cleanup

### Delete the CloudFormation stack

```bash
sam delete --stack-name toll-free-reg-auto
```

### Release phone numbers (if not deleted by stack)

```bash
aws pinpoint-sms-voice-v2 release-phone-number --phone-number-id <phone-number-id>
```

### Delete registrations (if not deleted by stack)

```bash
aws pinpoint-sms-voice-v2 delete-registration --registration-id <registration-id>
```

**Note:** The S3 upload bucket has versioning enabled. SAM expects to empty and delete it during stack deletion, but if deletion fails, you may need to manually empty the bucket first.

## Frequently Asked Questions

**Can I use this for multiple toll-free registrations?**
Yes. Each form submission creates an independent workflow. You can have as many in-flight registrations as you need.

**What happens if the registration is rejected?**
You receive an email notification with the rejection reason and instructions. Fix the issue in the AWS console, resubmit, and the workflow automatically resumes — or call the `/api/resume` endpoint.

**What are the costs?**
Infrastructure costs are minimal (a few cents per registration for Lambda, DynamoDB, and Step Functions). The main costs are the EUM SMS fees — a monthly phone number lease and any per-message charges. See [AWS End User Messaging Pricing](https://aws.amazon.com/end-user-messaging/pricing/) for current rates.

**Is my data secure?**
This solution includes security controls such as time-limited presigned URLs, encrypted S3 storage with TLS enforcement, per-function IAM roles, and DynamoDB encryption at rest. Under the [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/), you are responsible for restricting CORS origins, enabling CloudTrail, adding API authentication, and performing your own security assessment before production use. See the [Security Hardening Guide](toll-free-registration-automation-security-hardening.md) for details.
