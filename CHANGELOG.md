<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# Changelog

## [Unreleased]

### Security
- **IAM authorization on the API** — every route now requires a SigV4-signed request with `execute-api:Invoke`. Previously the API was open, and any caller with the URL could buy a toll-free number. Integration test helpers sign their requests, and the docs use `curl --aws-sigv4`.
- Added `SECURITY.md`
- `samconfig.toml` uses a placeholder `AllowedOrigin` instead of `*`
- Pinned test dependencies to exact versions
- `AllowedOrigin` is required and has no default. An `AllowedPattern` rejects `*` and blank values, so pass a full `http` or `https` origin such as `https://app.example.com`

### Fixed
- **Rejection reason missing from emails**: the notification Lambda read `DeniedReasonMessage`, which the API does not return. It now reads `DeniedReasons` from the latest registration version.
- **Silent workflow failures**: `RequestPhoneNumber`, `CreateAndSubmitRegistration` and `WaitForHumanIntervention` now catch errors and send a failure notification. A second rejection during human intervention returns to the rejection path instead of failing the execution.
- **Attachment upload check**: the registration Lambda stops if an attachment is not `UPLOAD_COMPLETE` after 30 seconds, instead of assigning it anyway
- **Presigned URL permissions**: the function can only `s3:PutObject` under `uploads/`, replacing `S3CrudPolicy`
- **Wizard field path labels**: `taxId`, `taxIdAuthority`, `taxIdCountry` and `optInDescription` now match the generated commands and the API
- **Integration tests**: the payload uses the field names the intake API requires, the default region matches `samconfig.toml`, and completion is checked against the Step Functions execution status
- **Docs**: the dry-run command includes `NotificationEmail`, the resume example no longer doubles `/prod`, the README describes the wizard as a CLI command generator, and Cleanup stops running executions before `sam delete`
- **Wizard field path bug** — `companyInfo.country` corrected to `companyInfo.isoCountryCode` to match the API field path for US_TOLL_FREE_REGISTRATION
- **Wizard enum mismatch** — `APPOINTMENT_REMINDERS` corrected to `APPOINTMENT` and `BOOKING_CONFIRMATIONS` corrected to `BOOKING` to match valid API select choices for `messagingUseCase.useCaseCategory`

### Added
- Complete Lambda implementations for all 6 functions (intake, registration, event router, notification, presigned URL, resume)
- SAM template with full infrastructure (DynamoDB, S3, SNS, API Gateway, EventBridge, Step Functions)
- Submission confirmation notification — immediate email when registration is submitted with phone number and registration ID
- Unit tests for all Lambda functions (36 tests)
- Integration test suite with orchestrator and event simulator
- Test event fixtures for `sam local invoke` (9 JSON files)
- Security design document with data classification, encryption strategy, and IAM design
- Architecture diagram description document
- User guide with deployment, configuration, monitoring, and cleanup instructions
- Security hardening guide with 5 prioritized steps
- ADR-001 through ADR-005 documenting all accepted risks and false positives
- Copyright and license headers on all source files

### Changed
- Dry run module: fixed `NumberType` from `TEN_DLC` to `TOLL_FREE` and synthetic phone number to `+18005550199`
- Replaced deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)` in all Lambda functions

### Security
- **Path traversal prevention** — presigned URL Lambda sanitizes `fieldName` parameter, rejecting path separators and directory traversal sequences
- **Enhanced input validation** — intake Lambda validates required field presence, types, and lengths
- **EUM SMS IAM scoping:** every `sms-voice` statement is now scoped to `arn:{partition}:sms-voice:{region}:{account}:{type}/*`, one statement per resource type, replacing the earlier `Resource: '*'`. The previous rationale that these actions do not support resource-level permissions was incorrect; the user guide lists a resource ARN for each of them (ADR-001, rewritten)
- **False positive:** "AWS End User Messaging SMS" is the official service name (ADR-002)
- **Accepted risk:** S3 MFA Delete cannot be enabled via CloudFormation (ADR-003)
- **By design:** Registration Lambda error handling propagates exceptions for Step Functions routing (ADR-004)
- **By design:** Security scan results stored locally, not committed to repository (ADR-005)
- **Access logging chain completed:** the access logs bucket now logs to itself under a separate prefix, with versioning and lifecycle expiry (ADR-008)
- **Encryption at rest:** DynamoDB table now uses a customer managed KMS key with rotation enabled, and the SNS topic uses `alias/aws/sns` (ADR-009)
- **CSP hardened:** the wizard front end runs without `'unsafe-inline'` in `script-src` or `style-src`, split into HTML, CSS, and JS with handlers attached via `addEventListener` (ADR-010)
- **Example phone numbers:** all phone numbers in the repository moved into the NANP reserved range `555-0100` to `555-0199` so no sample command can reach a real subscriber (ADR-011)
- **S3 TLS enforcement:** `aws:SecureTransport` condition value changed from the string `'false'` to the boolean `false` in both bucket policies. CloudFormation accepts either, but policy scanners only recognize the boolean form.
