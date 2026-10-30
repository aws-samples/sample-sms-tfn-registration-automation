# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Intake Lambda - receives form submission from API Gateway,
validates input, writes to DynamoDB, and starts Step Functions execution.
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3

dynamodb = boto3.resource('dynamodb')
sfn = boto3.client('stepfunctions')
table = dynamodb.Table(os.environ['REGISTRATIONS_TABLE'])
STATE_MACHINE_ARN = os.environ['STATE_MACHINE_ARN']

# Required for new US toll-free registrations since 15 September 2026
REQUIRED_URL_FIELDS = ['privacyPolicyUrl', 'termsAndConditionsUrl']

# Stricter than the API pattern for these fields, so a URL that passes here
# also passes PutRegistrationFieldValue (which runs after the number is bought)
URL_PATTERN = re.compile(
    r'https?://[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?\.[A-Za-z]{2,63}(?:[/?#:]\S*)?'
)


def handler(event, context):
    # Parse body
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError) as exc:
        return _error(400, f'Invalid JSON in request body: {exc}')

    # Validate companyFields
    company_fields = body.get('companyFields')
    if not company_fields or not isinstance(company_fields, dict):
        return _error(400, 'companyFields is required and must be an object')

    # Validate contactFields
    contact_fields = body.get('contactFields')
    if not contact_fields or not isinstance(contact_fields, dict):
        return _error(400, 'contactFields is required and must be an object')

    # Validate required company fields
    required_company = ['companyName', 'website', 'address1', 'city', 'state', 'zipCode', 'country']
    missing_company = [f for f in required_company if not company_fields.get(f)]
    if missing_company:
        return _error(400, f'Missing required company fields: {", ".join(missing_company)}')

    # Validate required contact fields
    required_contact = ['firstName', 'lastName', 'supportEmail', 'supportPhoneNumber']
    missing_contact = [f for f in required_contact if not contact_fields.get(f)]
    if missing_contact:
        return _error(400, f'Missing required contact fields: {", ".join(missing_contact)}')

    # Validate field value types and lengths
    for section_name, section in [('companyFields', company_fields), ('contactFields', contact_fields)]:
        for key, value in section.items():
            if not isinstance(value, str):
                return _error(400, f'{section_name}.{key} must be a string')
            if len(value) > 500:
                return _error(400, f'{section_name}.{key} exceeds maximum length of 500 characters')

    # Validate useCaseFields and the required URL fields
    use_case_fields = body.get('useCaseFields')
    if not use_case_fields or not isinstance(use_case_fields, dict):
        return _error(400, 'useCaseFields is required and must be an object')

    missing_urls = [f for f in REQUIRED_URL_FIELDS if not use_case_fields.get(f)]
    if missing_urls:
        return _error(400, f'Missing required use case fields: {", ".join(missing_urls)}')

    for key in REQUIRED_URL_FIELDS:
        value = use_case_fields[key]
        if not isinstance(value, str) or not 12 <= len(value) <= 500 or not URL_PATTERN.fullmatch(value):
            return _error(400, f'useCaseFields.{key} must be an http or https URL of 12 to 500 characters')

    request_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    # Store the full registration request in DynamoDB
    item = {
        'requestId': request_id,
        'status': 'SUBMITTED',
        'createdAt': now,
        'updatedAt': now,
        'companyFields': company_fields,
        'contactFields': contact_fields,
        'useCaseFields': use_case_fields,
        'messageSamples': body.get('messageSamples', {}),
        'attachments': body.get('attachments', {}),
        'phoneConfig': body.get('phoneConfig', {}),
        # Will be populated as registration progresses
        'registrationId': '-',
        'phoneNumberId': '-',
        'taskTokens': {},
    }

    try:
        table.put_item(Item=item)
    except Exception as exc:
        return _error(500, f'Failed to store registration: {exc}')

    try:
        sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=f'reg-{request_id}',
            input=json.dumps({'requestId': request_id}),
        )
    except Exception as exc:
        return _error(500, f'Failed to start workflow: {exc}')

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'requestId': request_id,
            'message': 'Registration workflow started',
        }),
    }


def _error(status_code, message):
    """Return an API Gateway-compatible error response."""
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'error': message}),
    }
