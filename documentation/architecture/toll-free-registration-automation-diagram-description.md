<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# Toll-Free Registration Automation — Architecture Diagram Description

Use this description to create or update the system architecture diagram in draw.io.
Use official AWS Architecture Icons (2024+).

---

## Diagram Layout

The diagram has 4 horizontal swim lanes flowing left to right:

1. **Client Layer** (left)
2. **API Layer** (center-left)
3. **Orchestration Layer** (center)
4. **AWS Services Layer** (right)

Plus a **Callback Loop** that flows from right back to center.

---

## Components and Connections

### Client Layer

**Component: Registration Wizard (Static HTML)**
- Icon: User / Browser
- Label: "Registration Wizard (Static HTML)"
- Two outbound arrows:
  1. Arrow to Amazon API Gateway labeled "POST /api/submit (form data)"
  2. Arrow to Amazon S3 labeled "PUT (presigned URL upload)"

---

### API Layer

**Component: Amazon API Gateway (HTTP API)**
- Icon: Amazon API Gateway
- Label: "Amazon API Gateway (HTTP API)"
- Three outbound arrows to Lambda functions:
  1. "POST /api/submit" → Intake Lambda
  2. "POST /api/upload-url" → Presigned URL Lambda
  3. "POST /api/resume/{id}" → Resume Lambda

**Component: Intake Lambda**
- Icon: AWS Lambda
- Label: "IntakeFunction"
- Two outbound arrows:
  1. Arrow to Amazon DynamoDB labeled "Write registration data"
  2. Arrow to AWS Step Functions labeled "StartExecution"

**Component: Presigned URL Lambda**
- Icon: AWS Lambda
- Label: "PresignedUrlFunction"
- One outbound arrow:
  1. Arrow to Amazon S3 labeled "Generate presigned PUT URL"

**Component: Resume Lambda**
- Icon: AWS Lambda
- Label: "ResumeFunction"
- Two outbound arrows:
  1. Arrow to Amazon DynamoDB labeled "Read task token"
  2. Arrow to AWS Step Functions labeled "SendTaskSuccess"

---

### Orchestration Layer

**Component: AWS Step Functions (Standard Workflow)**
- Icon: AWS Step Functions
- Label: "Registration Workflow (Standard)"
- This is the central component. Show it as a large box with the internal state flow.

**Internal State Flow (vertical flowchart inside the Step Functions box):**

```
[Start]
   │
   v
[RequestPhoneNumber] ──> Registration Lambda (request toll-free number)
   │                         (on API error ──> [NotifyErrored] ──> SNS ──> [WorkflowFailed])
   v
[CreateAndSubmitRegistration] ──> Registration Lambda (create reg, associate phone
   │                               (BEFORE_SUBMIT), populate fields, submit)
   │                               (on API error ──> [NotifyErrored] ──> SNS ──> [WorkflowFailed])
   v
[NotifySubmitted] ──> Notification Lambda ──> SNS
   │
   v
[WaitForApproval] <── waitForTaskToken (pauses here, up to 30 days)
   │
   ├── (on rejection)
   │       │
   │       v
   │   [RegistrationRejected] ──> Notification Lambda ──> SNS
   │       │
   │       v
   │   [WaitForHumanIntervention] <── waitForTaskToken (pauses for operator)
   │       │   (rejected again ──> back to [RegistrationRejected];
   │       │    closed, deleted or step error ──> [NotifyErrored] ──> SNS ──> [WorkflowFailed])
   │       v (EventBridge callback or POST /api/resume)
   │
   ├── (on timeout ──> [RegistrationTimedOut] ──> SNS ──> [RegistrationFailed])
   │
   v (on approval)
[NotifyComplete] ──> Notification Lambda ──> SNS
   │
   v
[RegistrationComplete - Success]
```

**Outbound arrows from Step Functions to Lambda functions:**
1. Arrow to Registration Lambda labeled "request phone; create reg, associate phone (BEFORE_SUBMIT), populate fields, submit"
2. Arrow to Notification Lambda labeled "notify (submitted / rejected / complete / timed out / errored)"

---

### AWS Services Layer (right side)

**Component: Amazon DynamoDB**
- Icon: Amazon DynamoDB
- Label: "Registrations Table"
- Receives arrows from: Intake, Registration, Event Router, Notification (read), Resume
- Note: "Stores registration state, form data, task tokens"
- Show GSI: "registration-id-index"

**Component: Amazon S3**
- Icon: Amazon S3
- Label: "Upload Bucket (encrypted, versioned)"
- Receives arrows from: Browser (presigned URL upload), Registration Lambda (read attachments)
- Second smaller S3 icon labeled "Access Logs Bucket"

**Component: Amazon SNS**
- Icon: Amazon SNS
- Label: "Notification Topic"
- Receives arrow from: Notification Lambda
- Outbound arrow to: Email icon labeled "Operator Email"

**Component: AWS End User Messaging SMS**
- Icon: Use the generic AWS icon (no specific icon exists yet)
- Label: "AWS End User Messaging SMS"
- Receives arrows from: Registration Lambda, Notification Lambda (describe)
- Labels on arrows: "RequestPhoneNumber, CreateRegistration, CreateRegistrationAssociation, PutRegistrationFieldValue, CreateRegistrationAttachment, SubmitRegistrationVersion"

---

### Callback Loop (the key architectural pattern)

**Component: Amazon EventBridge**
- Icon: Amazon EventBridge
- Label: "EventBridge (Default Bus)"
- Inbound arrow from: AWS End User Messaging SMS labeled "Registration Status Change events"
- Outbound arrow to: Event Router Lambda

**Component: Event Router Lambda**
- Icon: AWS Lambda
- Label: "EventRouterFunction"
- Inbound arrow from: Amazon EventBridge
- Two outbound arrows:
  1. Arrow to Amazon DynamoDB labeled "Lookup task token (via GSI)"
  2. Arrow to AWS Step Functions labeled "SendTaskSuccess / SendTaskFailure"

**Show the callback loop as a distinct colored path:**
```
AWS End User Messaging SMS ──> EventBridge ──> Event Router Lambda ──> DynamoDB (lookup token) ──> Step Functions (resume)
```
This loop is what makes the multi-week toll-free registration workflow possible
without polling.

---

## Security Boundaries

Annotate the diagram with these security boundary boxes:

### Public Boundary (outermost)
- Contains: Browser
- Label: "Public — untrusted"

### API Gateway Boundary
- Contains: Amazon API Gateway
- Label: "HTTPS only, CORS configurable, IAM (SigV4) required on every route"

### Lambda Execution Boundary
- Contains: All 6 Lambda functions
- Label: "Per-function IAM roles, least privilege"

### Data Store Boundary
- Contains: DynamoDB, S3 (both buckets)
- Label: "Encrypted at rest, IAM-only access"

---

## Security Annotations

Add these as small callout boxes or annotations:

- On the S3 upload bucket: "AES-256 encryption, TLS enforced, versioning enabled, Block Public Access, 90-day lifecycle"
- On the API Gateway: "HTTPS only, CORS configurable"
- On DynamoDB: "Encryption at rest (SSE), PITR enabled"
- On the presigned URL arrow: "Time-limited expiry, PNG/JPEG/PDF only, 500 KB max"
- On each Lambda: "Per-function IAM role"
- On the EventBridge rule: "Scoped to aws.sms-voice source, Registration Status Change events"

---

## Color Coding Suggestion

- **Green arrows:** Happy path (approval flow)
- **Red arrows:** Rejection/failure path
- **Orange arrows:** Human intervention (resume) path
- **Blue arrows:** EventBridge callback loop
- **Gray arrows:** Data storage (DynamoDB, S3)

---

## Diagram Title

"Toll-Free Registration Automation — System Architecture"

Subtitle: "AWS Step Functions orchestrates toll-free number registration with
event-driven callbacks via Amazon EventBridge"
