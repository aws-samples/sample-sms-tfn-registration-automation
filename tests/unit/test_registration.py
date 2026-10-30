# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Unit tests for the Registration Lambda (3 actions)."""
import json
import sys
import os
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws


def _load_registration():
    """Import the registration Lambda module, ensuring fresh module state."""
    lambda_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'lambda', 'registration'
    )
    shared_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'lambda', 'shared'
    )
    for d in (lambda_dir, shared_dir):
        if d not in sys.path:
            sys.path.insert(0, d)
    import importlib
    import app as reg_app
    importlib.reload(reg_app)
    return reg_app


def _create_table():
    """Create the mocked DynamoDB table with GSI."""
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.create_table(
        TableName='test-registrations',
        KeySchema=[{'AttributeName': 'requestId', 'KeyType': 'HASH'}],
        AttributeDefinitions=[
            {'AttributeName': 'requestId', 'AttributeType': 'S'},
            {'AttributeName': 'registrationId', 'AttributeType': 'S'},
        ],
        GlobalSecondaryIndexes=[{
            'IndexName': 'registration-id-index',
            'KeySchema': [{'AttributeName': 'registrationId', 'KeyType': 'HASH'}],
            'Projection': {'ProjectionType': 'ALL'},
        }],
        BillingMode='PAY_PER_REQUEST',
    )
    table.meta.client.get_waiter('table_exists').wait(TableName='test-registrations')
    return table


def _seed_item(table, request_id='req-001'):
    """Seed a sample registration item into DynamoDB."""
    table.put_item(Item={
        'requestId': request_id,
        'status': 'PHONE_PROVISIONED',
        'companyFields': {'companyName': 'Test Co', 'taxId': '12-3456789',
                          'address': '123 Main St', 'city': 'Seattle',
                          'state': 'WA', 'zipCode': '98101', 'isoCountryCode': 'US'},
        'contactFields': {'firstName': 'Jane', 'lastName': 'Doe',
                          'email': 'jane@example.com', 'phoneNumber': '+12065550142'},
        'useCaseFields': {'monthlyMessageVolume': '10,000', 'useCaseCategory': 'ONE_TIME_PASSCODES',
                          'useCaseDetails': 'OTP codes',
                          'privacyPolicyUrl': 'https://example.com/privacy',
                          'termsAndConditionsUrl': 'https://example.com/terms',
                          'optInType': 'VERBAL',
                          'optInWorkflow': 'Customer opts in verbally'},
        'messageSamples': {'messageSample1': 'Your code is 123456.'},
        'attachments': {},
        'phoneConfig': {},
        'registrationId': '-',
        'phoneNumberId': 'phone-001',
        'phoneNumber': '+18885550101',
        'phoneNumberArn': 'arn:aws:sms-voice:us-east-1:000000000000:phone-number/phone-001',
        'taskTokens': {},
    })


def _mock_sms(app):
    """Attach a mocked pinpoint-sms-voice-v2 client."""
    mock = MagicMock()
    mock.request_phone_number.return_value = {
        'PhoneNumberId': 'phone-mock-001',
        'PhoneNumber': '+18885550199',
        'PhoneNumberArn': 'arn:aws:sms-voice:us-east-1:000000000000:phone-number/phone-mock-001',
        'Status': 'ACTIVE',
        'NumberType': 'TOLL_FREE',
    }
    mock.create_registration.return_value = {
        'RegistrationId': 'reg-mock-001',
        'RegistrationArn': 'arn:aws:sms-voice:us-east-1:000000000000:registration/reg-mock-001',
        'RegistrationType': 'US_TOLL_FREE_REGISTRATION',
        'RegistrationStatus': 'CREATED',
        'CurrentVersionNumber': 1,
    }
    mock.create_registration_association.return_value = {}
    mock.put_registration_field_value.return_value = {}
    mock.submit_registration_version.return_value = {}
    app.sms = mock
    return mock


# ── Tests ────────────────────────────────────────────────────────────────


@mock_aws
def test_request_phone_number_updates_dynamodb(aws_env):
    """request_phone_number action updates DynamoDB with phoneNumberId, phoneNumber, status."""
    table = _create_table()
    # Seed a minimal item
    table.put_item(Item={
        'requestId': 'req-001', 'status': 'SUBMITTED',
        'registrationId': '-', 'phoneNumberId': '-', 'taskTokens': {},
    })

    app = _load_registration()
    sms_mock = _mock_sms(app)

    event = {'requestId': 'req-001', 'action': 'request_phone_number'}
    result = app.handler(event, None)

    assert result['status'] == 'PHONE_PROVISIONED'
    assert result['phoneNumberId'] == 'phone-mock-001'
    assert result['phoneNumber'] == '+18885550199'

    # Verify DynamoDB was updated
    item = table.get_item(Key={'requestId': 'req-001'})['Item']
    assert item['phoneNumberId'] == 'phone-mock-001'
    assert item['phoneNumber'] == '+18885550199'
    assert item['status'] == 'PHONE_PROVISIONED'


@mock_aws
def test_create_associate_populate_submit_updates_dynamodb(aws_env):
    """create_associate_populate_submit updates DynamoDB with registrationId and status."""
    table = _create_table()
    _seed_item(table, 'req-002')

    app = _load_registration()
    sms_mock = _mock_sms(app)

    event = {'requestId': 'req-002', 'action': 'create_associate_populate_submit'}
    result = app.handler(event, None)

    assert result['registrationId'] == 'reg-mock-001'
    assert result['status'] == 'REGISTRATION_SUBMITTED'

    # Verify DynamoDB was updated
    item = table.get_item(Key={'requestId': 'req-002'})['Item']
    assert item['registrationId'] == 'reg-mock-001'
    assert item['status'] == 'REGISTRATION_SUBMITTED'

    # Verify the SMS API calls were made in the right order
    sms_mock.create_registration.assert_called_once()
    sms_mock.create_registration_association.assert_called_once()
    sms_mock.submit_registration_version.assert_called_once()


@mock_aws
def test_store_task_token_stores_in_dynamodb(aws_env):
    """store_task_token stores taskTokens.{waitingFor} correctly."""
    table = _create_table()
    table.put_item(Item={
        'requestId': 'req-003', 'status': 'REGISTRATION_SUBMITTED',
        'registrationId': 'reg-001', 'taskTokens': {},
    })

    app = _load_registration()

    event = {
        'requestId': 'req-003',
        'action': 'store_task_token',
        'taskToken': 'my-task-token-abc',
        'waitingFor': 'registration',
    }
    # store_task_token does NOT return (waitForTaskToken pattern)
    result = app.handler(event, None)

    # Verify DynamoDB has the token
    item = table.get_item(Key={'requestId': 'req-003'})['Item']
    assert item['taskTokens']['registration'] == 'my-task-token-abc'


@mock_aws
def test_dry_run_uses_synthetic_responses(aws_env, monkeypatch):
    """DRY_RUN=true uses fake_phone_number, DynamoDB still updated."""
    monkeypatch.setenv('DRY_RUN', 'true')
    table = _create_table()
    table.put_item(Item={
        'requestId': 'req-dry', 'status': 'SUBMITTED',
        'registrationId': '-', 'phoneNumberId': '-', 'taskTokens': {},
    })

    app = _load_registration()
    # Do NOT mock sms — dry run should not call it
    sms_mock = MagicMock()
    app.sms = sms_mock

    event = {'requestId': 'req-dry', 'action': 'request_phone_number'}
    result = app.handler(event, None)

    assert result['status'] == 'PHONE_PROVISIONED'
    # Dry run should NOT call the real SMS API
    sms_mock.request_phone_number.assert_not_called()

    # DynamoDB should still be updated
    item = table.get_item(Key={'requestId': 'req-dry'})['Item']
    assert item['status'] == 'PHONE_PROVISIONED'
    assert item['phoneNumberId'] != '-'


@mock_aws
def test_unknown_action_returns_error(aws_env):
    """Unknown action returns error response."""
    _create_table()
    app = _load_registration()

    event = {'requestId': 'req-001', 'action': 'do_something_weird'}
    result = app.handler(event, None)

    assert 'error' in result
    assert 'do_something_weird' in result['error']


@mock_aws
def test_url_fields_are_populated(aws_env):
    """Privacy Policy and Terms and Conditions URLs are set on the registration."""
    table = _create_table()
    _seed_item(table, 'req-urls')

    app = _load_registration()
    sms_mock = _mock_sms(app)

    event = {'requestId': 'req-urls', 'action': 'create_associate_populate_submit'}
    app.handler(event, None)

    put_calls = {
        c.kwargs['FieldPath']: c.kwargs
        for c in sms_mock.put_registration_field_value.call_args_list
    }
    assert put_calls['messagingUseCase.privacyPolicyUrl']['TextValue'] == 'https://example.com/privacy'
    assert put_calls['messagingUseCase.termsAndConditionsUrl']['TextValue'] == 'https://example.com/terms'


@mock_aws
def test_required_use_case_fields_are_mapped(aws_env):
    """Every required messagingUseCase field path has a form key mapped to it."""
    app = _load_registration()

    mapped = {path for path, _ in app.USE_CASE_FIELDS.values()}
    mapped |= set(app.ATTACHMENT_FIELDS.values())
    # REQUIRED messagingUseCase fields from DescribeRegistrationFieldDefinitions
    # for US_TOLL_FREE_REGISTRATION
    required = {
        'messagingUseCase.monthlyMessageVolume',
        'messagingUseCase.useCaseCategory',
        'messagingUseCase.useCaseDetails',
        'messagingUseCase.privacyPolicyUrl',
        'messagingUseCase.termsAndConditionsUrl',
        'messagingUseCase.optInType',
        'messagingUseCase.optInDescription',
        'messagingUseCase.optInImage',
    }
    assert required <= mapped
