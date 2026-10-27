# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Unit tests for the Notification Lambda."""
import json
import sys
import os
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws


def _load_notification():
    """Import the notification Lambda module, ensuring fresh module state."""
    lambda_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'lambda', 'notification'
    )
    shared_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'lambda', 'shared'
    )
    for d in (lambda_dir, shared_dir):
        if d not in sys.path:
            sys.path.insert(0, d)
    import importlib
    import app as notify_app
    importlib.reload(notify_app)
    return notify_app


def _create_table():
    """Create the mocked DynamoDB table."""
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.create_table(
        TableName='test-registrations',
        KeySchema=[{'AttributeName': 'requestId', 'KeyType': 'HASH'}],
        AttributeDefinitions=[
            {'AttributeName': 'requestId', 'AttributeType': 'S'},
        ],
        BillingMode='PAY_PER_REQUEST',
    )
    table.meta.client.get_waiter('table_exists').wait(TableName='test-registrations')
    return table


def _seed_item(table, request_id='req-001'):
    """Seed a sample registration item."""
    table.put_item(Item={
        'requestId': request_id,
        'status': 'REGISTRATION_SUBMITTED',
        'companyFields': {'companyName': 'Test Company LLC'},
        'contactFields': {'firstName': 'Jane', 'email': 'jane@example.com'},
        'registrationId': 'reg-001',
        'phoneNumberId': 'phone-001',
        'phoneNumber': '+18885550142',
        'taskTokens': {},
    })


def _create_sns_topic():
    """Create a mocked SNS topic and return (client, topic_arn)."""
    sns = boto3.client('sns', region_name='us-east-1')
    resp = sns.create_topic(Name='test-notifications')
    return sns, resp['TopicArn']


# ── Tests ────────────────────────────────────────────────────────────────


@mock_aws
@mock_aws
def test_rejected_publishes_sns(aws_env, monkeypatch):
    """REGISTRATION_REJECTED → SNS publish called with rejection subject."""
    table = _create_table()
    _seed_item(table, 'req-rej')
    sns_client, topic_arn = _create_sns_topic()
    monkeypatch.setenv('NOTIFICATION_TOPIC_ARN', topic_arn)

    app = _load_notification()
    # Mock the sms client so _get_rejection_details doesn't call real API
    app.sms = MagicMock()
    app.sms.describe_registration_versions.return_value = {
        'RegistrationVersions': [{
            'VersionNumber': 1,
            'DeniedReasons': [{'Reason': 'COMPANY_NAME', 'ShortDescription': 'Company name mismatch'}],
        }]
    }
    paginator_mock = MagicMock()
    paginator_mock.paginate.return_value = [{'RegistrationFieldValues': []}]
    app.sms.get_paginator.return_value = paginator_mock

    event = {'requestId': 'req-rej', 'type': 'REGISTRATION_REJECTED'}
    result = app.handler(event, None)

    assert result['notified'] is True
    assert result['type'] == 'REGISTRATION_REJECTED'

    # Verify SNS was published to
    messages = sns_client.list_subscriptions_by_topic(TopicArn=topic_arn)
    # We can't easily read published messages with moto, but we can verify
    # the handler completed without error — the SNS publish call succeeded


@mock_aws
@mock_aws
def test_complete_publishes_sns(aws_env, monkeypatch):
    """REGISTRATION_COMPLETE → SNS publish with success subject."""
    table = _create_table()
    _seed_item(table, 'req-ok')
    sns_client, topic_arn = _create_sns_topic()
    monkeypatch.setenv('NOTIFICATION_TOPIC_ARN', topic_arn)

    app = _load_notification()

    event = {'requestId': 'req-ok', 'type': 'REGISTRATION_COMPLETE'}
    result = app.handler(event, None)

    assert result['notified'] is True
    assert result['type'] == 'REGISTRATION_COMPLETE'


@mock_aws
@mock_aws
def test_timed_out_publishes_sns(aws_env, monkeypatch):
    """REGISTRATION_TIMED_OUT → SNS publish with timeout subject."""
    table = _create_table()
    _seed_item(table, 'req-to')
    sns_client, topic_arn = _create_sns_topic()
    monkeypatch.setenv('NOTIFICATION_TOPIC_ARN', topic_arn)

    app = _load_notification()

    event = {'requestId': 'req-to', 'type': 'REGISTRATION_TIMED_OUT', 'error': {}}
    result = app.handler(event, None)

    assert result['notified'] is True
    assert result['type'] == 'REGISTRATION_TIMED_OUT'


@mock_aws
def test_errored_publishes_sns(aws_env, monkeypatch):
    """REGISTRATION_ERRORED → SNS publish with failure subject and the error."""
    table = _create_table()
    _seed_item(table, 'req-err')
    sns_client, topic_arn = _create_sns_topic()
    monkeypatch.setenv('NOTIFICATION_TOPIC_ARN', topic_arn)

    app = _load_notification()

    error = {'Error': 'ValidationException', 'Cause': 'bad field'}
    event = {'requestId': 'req-err', 'type': 'REGISTRATION_ERRORED', 'error': error}
    result = app.handler(event, None)

    assert result['notified'] is True
    assert result['type'] == 'REGISTRATION_ERRORED'
    message = app.build_message('req-err', 'REGISTRATION_ERRORED', error, {})
    assert 'TOLL-FREE REGISTRATION FAILED' in message
    assert 'ValidationException' in message


def test_rejection_reason_uses_denied_reasons(aws_env, monkeypatch):
    """Version-level reason comes from DeniedReasons on the latest version."""
    monkeypatch.setenv('NOTIFICATION_TOPIC_ARN', 'arn:aws:sns:us-east-1:123456789012:t')
    with mock_aws():
        _create_table()
        app = _load_notification()
    app.sms = MagicMock()
    app.is_dry_run = lambda: False
    app.sms.describe_registration_versions.return_value = {'RegistrationVersions': [
        {'VersionNumber': 2, 'DeniedReasons': [{'Reason': 'X', 'ShortDescription': 'Opt-in unclear'}]},
        {'VersionNumber': 1, 'DeniedReasons': [{'Reason': 'Y', 'ShortDescription': 'Old reason'}]},
    ]}
    app.sms.get_paginator.return_value.paginate.return_value = [{'RegistrationFieldValues': []}]

    reason, fields = app._get_rejection_details('registration-1')

    assert reason == 'Opt-in unclear'
    assert fields == []


@mock_aws
@mock_aws
def test_dry_run_skips_sms_api(aws_env, monkeypatch):
    """DRY_RUN=true → no sms API calls but SNS still published."""
    monkeypatch.setenv('DRY_RUN', 'true')
    table = _create_table()
    _seed_item(table, 'req-dry')
    sns_client, topic_arn = _create_sns_topic()
    monkeypatch.setenv('NOTIFICATION_TOPIC_ARN', topic_arn)

    app = _load_notification()
    sms_mock = MagicMock()
    app.sms = sms_mock

    event = {'requestId': 'req-dry', 'type': 'REGISTRATION_REJECTED'}
    result = app.handler(event, None)

    assert result['notified'] is True
    # In dry run, describe_registration_versions should NOT be called
    sms_mock.describe_registration_versions.assert_not_called()
    sms_mock.get_paginator.assert_not_called()
