# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Notification Lambda - sends SNS alerts for registration status changes.
Pulls rejection details from the AWS End User Messaging SMS API.

Notification types:
  - REGISTRATION_REJECTED: Registration requires updates
  - REGISTRATION_COMPLETE: Phone number provisioned and registration approved
  - REGISTRATION_TIMED_OUT: Approval wait exceeded timeout
  - REGISTRATION_ERRORED: An EUM SMS API call or workflow step failed
"""
import json
import os

import boto3

from dry_run import is_dry_run

sns = boto3.client('sns')
sms = boto3.client('pinpoint-sms-voice-v2')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['REGISTRATIONS_TABLE'])
TOPIC_ARN = os.environ['NOTIFICATION_TOPIC_ARN']

SUBJECTS = {
    'REGISTRATION_SUBMITTED': '[INFO] Toll-Free Registration Submitted',
    'REGISTRATION_REJECTED': '[WARNING] Toll-Free Registration Requires Updates',
    'REGISTRATION_COMPLETE': '[SUCCESS] Toll-Free Registration Complete',
    'REGISTRATION_TIMED_OUT': '[ERROR] Toll-Free Registration Timed Out',
    'REGISTRATION_ERRORED': '[ERROR] Toll-Free Registration Failed',
}


def handler(event, context):
    payload = event.get('Payload', event)
    request_id = payload.get('requestId', 'unknown')
    notification_type = payload.get('type', 'UNKNOWN')
    error = payload.get('error', {})

    item = _get_item(request_id)

    subject = SUBJECTS.get(notification_type, f'Toll-Free Registration Update: {notification_type}')
    message = build_message(request_id, notification_type, error, item)

    sns.publish(
        TopicArn=TOPIC_ARN,
        Subject=subject[:100],
        Message=message,
    )

    return {'notified': True, 'type': notification_type}


def _get_item(request_id):
    """Fetch the request record from DynamoDB."""
    try:
        resp = table.get_item(Key={'requestId': request_id})
        return resp.get('Item', {})
    except Exception:
        return {}


def _get_rejection_details(registration_id):
    """Query EUM SMS API for rejection details. Skipped in dry run."""
    if is_dry_run() or not registration_id or registration_id == '-':
        return None, []

    version_reason = None
    denied_fields = []

    try:
        resp = sms.describe_registration_versions(RegistrationId=registration_id)
        versions = resp.get('RegistrationVersions', [])
        if versions:
            latest = max(versions, key=lambda v: v.get('VersionNumber', 0))
            reasons = [
                r.get('ShortDescription') or r.get('Reason')
                for r in latest.get('DeniedReasons', [])
            ]
            version_reason = '; '.join(r for r in reasons if r) or None
    except Exception as e:
        print(f'Warning: Could not fetch registration versions for {registration_id}: {e}')

    try:
        paginator = sms.get_paginator('describe_registration_field_values')
        for page in paginator.paginate(RegistrationId=registration_id):
            for field in page.get('RegistrationFieldValues', []):
                denied_reason = field.get('DeniedReason')
                if denied_reason:
                    denied_fields.append({
                        'fieldPath': field.get('FieldPath', 'unknown'),
                        'reason': denied_reason,
                    })
    except Exception as e:
        print(f'Warning: Could not fetch field values for {registration_id}: {e}')

    return version_reason, denied_fields


def _format_rejection_details(registration_id):
    """Format rejection details into readable lines."""
    version_reason, denied_fields = _get_rejection_details(registration_id)
    lines = []

    if version_reason or denied_fields:
        lines.append('')
        lines.append('REJECTION DETAILS (from carrier review):')
        lines.append('-' * 30)

    if version_reason:
        lines.append(f'  Reason: {version_reason}')
        lines.append('')

    if denied_fields:
        lines.append('  Fields requiring correction:')
        for df in denied_fields:
            lines.append(f'    - {df["fieldPath"]}')
            lines.append(f'      Reason: {df["reason"]}')
        lines.append('')
    elif not version_reason:
        lines.append('')
        lines.append('  (No specific rejection details available from the API.')
        lines.append('   Check the registration in the AWS console for details.)')
        lines.append('')

    return lines


def build_message(request_id, notification_type, error, item):
    """Build the notification message body."""
    company_fields = item.get('companyFields', {})
    company_name = company_fields.get('companyName', 'Unknown')
    registration_id = item.get('registrationId', '-')

    lines = [
        'Toll-Free Registration Update',
        '=' * 50,
        '',
        f'Request ID:       {request_id}',
        f'Company:          {company_name}',
        f'Registration ID:  {registration_id}',
        f'Event:            {notification_type}',
        '',
    ]

    if notification_type == 'REGISTRATION_SUBMITTED':
        lines.extend(_registration_submitted(request_id, item))
    elif notification_type == 'REGISTRATION_REJECTED':
        lines.extend(_registration_rejected(request_id, registration_id))
    elif notification_type == 'REGISTRATION_COMPLETE':
        lines.extend(_registration_complete(request_id, item))
    elif notification_type == 'REGISTRATION_TIMED_OUT':
        lines.extend(_registration_timed_out(request_id, item, error))
    elif notification_type == 'REGISTRATION_ERRORED':
        lines.extend(_registration_errored(item, error))

    lines.extend([
        '',
        '-' * 50,
        'AWS End User Messaging SMS Console:',
        '  https://console.aws.amazon.com/sms-voice/home#/registrations',
        '',
        'This is an automated notification from the Toll-Free Registration Automation workflow.',
    ])

    return '\n'.join(lines)


def _registration_submitted(request_id, item):
    """Build submission confirmation content."""
    registration_id = item.get('registrationId', '-')
    phone_number = item.get('phoneNumber', '-')
    phone_number_id = item.get('phoneNumberId', '-')
    company_name = item.get('companyFields', {}).get('companyName', 'Unknown')
    use_case = item.get('useCaseFields', {}).get('useCaseCategory', '-')

    lines = [
        'TOLL-FREE REGISTRATION SUBMITTED SUCCESSFULLY',
        '-' * 30,
        '',
        'Your toll-free registration has been submitted for carrier review.',
        'No action is needed — you will be notified when the review is complete.',
        '',
        'Details:',
        f'  Company:          {company_name}',
        f'  Registration ID:  {registration_id}',
        f'  Phone Number:     {phone_number}',
        f'  Phone Number ID:  {phone_number_id}',
        f'  Use Case:         {use_case}',
        '',
        'What happens next:',
        '  - The carrier will review your registration (up to 15 business days)',
        '  - You will receive an email when the registration is approved or rejected',
        '  - If rejected, the email will include the reason and instructions to fix',
        '',
        'You can check the status at any time in the AWS console or by querying DynamoDB:',
        f'  Request ID: {request_id}',
    ]
    return lines


def _registration_rejected(request_id, registration_id):
    """Build rejection notification content."""
    lines = [
        'TOLL-FREE REGISTRATION REQUIRES UPDATES',
        '-' * 30,
        '',
        f'Registration ID: {registration_id}',
        '',
        'The toll-free registration was rejected and requires corrections.',
    ]
    lines.extend(_format_rejection_details(registration_id))
    lines.extend([
        'Common reasons for toll-free rejection:',
        '  - Company name does not match official records',
        '  - Invalid or mismatched tax ID (EIN)',
        '  - Opt-in workflow description is insufficient or unclear',
        '  - Message samples do not match the declared use case',
        '  - Opt-in screenshot does not show clear consent language',
        '',
        'To fix:',
        '  1. Open the registration in the AWS End User Messaging SMS console',
        '  2. Review the rejection details on the registration page',
        '  3. Correct the flagged fields and resubmit the registration version',
        '  4. Resume the workflow:',
        f'     POST /api/resume/{request_id}',
        '',
        'The workflow is PAUSED and waiting for your action.',
    ])
    return lines


def _registration_complete(request_id, item):
    """Build completion notification content."""
    registration_id = item.get('registrationId', '-')
    phone_number = item.get('phoneNumber', '-')
    phone_number_id = item.get('phoneNumberId', '-')
    company_name = item.get('companyFields', {}).get('companyName', 'Unknown')

    lines = [
        'TOLL-FREE REGISTRATION COMPLETE - READY TO SEND',
        '-' * 30,
        '',
        'Your toll-free registration is fully complete. The phone number',
        'is provisioned and the registration has been approved.',
        'You can now send messages.',
        '',
        'Summary:',
        f'  Company:          {company_name}',
        f'  Registration ID:  {registration_id}',
        '',
        'Phone Number:',
        f'  Number:    {phone_number}',
        f'  Number ID: {phone_number_id}',
        '',
        'Next steps:',
        '  - Use the phone number above as your origination identity',
        '  - Messages must match the declared use case and samples',
        '  - Monitor delivery rates in the AWS End User Messaging SMS console',
    ]
    return lines


def _registration_timed_out(request_id, item, error):
    """Build timeout notification content."""
    registration_id = item.get('registrationId', '-')
    status = item.get('status', 'UNKNOWN')

    lines = [
        'TOLL-FREE REGISTRATION TIMED OUT',
        '-' * 30,
        '',
        'The registration workflow timed out waiting for approval.',
        '',
        'Last known state:',
        f'  Status:          {status}',
        f'  Registration ID: {registration_id}',
        '',
        'This usually means the registration has been sitting in review',
        'longer than expected (30 days).',
        '',
        'To investigate:',
        '  1. Check the registration status in the AWS End User Messaging SMS console',
        '  2. If still under review, contact AWS Support',
        '  3. If rejected, fix and resubmit, then start a new workflow',
        '',
        f'Error: {json.dumps(error, indent=2)}',
    ]
    return lines


def _registration_errored(item, error):
    """Build failure notification content for an API or workflow error."""
    status = item.get('status', 'UNKNOWN')

    lines = [
        'TOLL-FREE REGISTRATION FAILED',
        '-' * 30,
        '',
        'The workflow stopped. An AWS End User Messaging SMS API call failed, a',
        'workflow step failed, or the registration was closed or deleted.',
        '',
        'Last known state:',
        f'  Status:          {status}',
        f'  Phone Number ID: {item.get("phoneNumberId", "-")}',
        f'  Registration ID: {item.get("registrationId", "-")}',
        '',
        'To investigate:',
        '  1. Read the error below and the Lambda logs in Amazon CloudWatch',
        '  2. Release any phone number and delete any registration you no longer need',
        '  3. Fix the cause and submit the request again',
        '',
        f'Error: {json.dumps(error, indent=2)}',
    ]
    return lines
