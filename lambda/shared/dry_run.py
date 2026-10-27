# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Dry-run helpers for testing without real AWS End User Messaging SMS API calls.

When DRY_RUN=true, functions return synthetic responses instead of
calling pinpoint-sms-voice-v2. Everything else (DynamoDB, Step Functions,
SNS, EventBridge routing) runs for real.
"""
import os
import uuid


def is_dry_run():
    return os.environ.get('DRY_RUN', 'false').lower() == 'true'


def fake_registration_id(prefix='registration'):
    return f'{prefix}-dryrun-{uuid.uuid4().hex[:12]}'


def fake_create_registration(reg_type):
    """Simulate create_registration response."""
    return {
        'RegistrationArn': f'arn:aws:sms-voice:us-east-1:000000000000:registration/{fake_registration_id()}',
        'RegistrationId': fake_registration_id(),
        'RegistrationType': reg_type,
        'RegistrationStatus': 'CREATED',
        'CurrentVersionNumber': 1,
    }


def fake_phone_number():
    """Simulate request_phone_number response."""
    pid = f'phone-dryrun-{uuid.uuid4().hex[:12]}'
    return {
        'PhoneNumberId': pid,
        'PhoneNumber': '+18005550199',
        'PhoneNumberArn': f'arn:aws:sms-voice:us-east-1:000000000000:phone-number/{pid}',
        'Status': 'ACTIVE',
        'IsoCountryCode': 'US',
        'MessageType': 'TRANSACTIONAL',
        'NumberCapabilities': ['SMS'],
        'NumberType': 'TOLL_FREE',
    }
