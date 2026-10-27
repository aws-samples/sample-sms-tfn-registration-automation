<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0 -->

# Security Policy

## Reporting a vulnerability

If you discover a potential security issue in this project, notify AWS Security
via the [vulnerability reporting page](https://aws.amazon.com/security/vulnerability-reporting/)
or email aws-security@amazon.com directly.

Please do not create a public GitHub issue for a security report.

## Scope

This is sample code for demonstration, not a production system. Read these
trade-offs before you deploy it:

- **Submitting a registration costs money.** Each submission requests a toll-free
  number, and the lease fee starts immediately. Deploy with `DryRun=true` until you
  are ready to register real numbers.
- **The API uses IAM authorization.** Any principal in the account with
  `execute-api:Invoke` on the API can submit registrations and resume workflows.
  Grant that permission only to operator roles. To call the API from a browser,
  replace IAM authorization with an Amazon Cognito JWT authorizer.
- **There is no request throttling beyond the API Gateway defaults.** Add route
  throttling or AWS WAF before giving more people access.
- **Registration data is business contact information.** The DynamoDB table holds
  company and contact details from the form, and the upload bucket holds opt-in
  screenshots for 90 days. Both are encrypted at rest. Do not put personal data
  you are not allowed to store in them.

See the [Security Design Document](documentation/architecture/toll-free-registration-automation-security-design.md)
and the [Security Hardening Guide](documentation/toll-free-registration-automation-security-hardening.md)
for the full threat boundaries and production hardening steps.

## Deploying safely

- Deploy into a sandbox or development AWS account, not a production account.
- Restrict `AllowedOrigin` to your own domain.
- Run `sam delete` when you are finished, then release any toll-free numbers and
  delete any registrations the workflow created. See [Cleanup](README.md#cleanup).
