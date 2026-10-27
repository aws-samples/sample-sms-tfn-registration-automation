# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Unit tests for the Event Router Lambda."""
import json
import sys
import os
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws


def _load_event_router():
    """Import the event_router Lambda module, ensuring fresh module state."""
    lambda_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'lambda', 'event_router'
    )
    if lambda_dir not in sys.path:
        sys.path.insert(0, lambda_dir)
    import importlib
    import app as router_app
    importlib.reload(router_app)
    return router_app


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


def _seed_item(table, request_id='req-001', registration_id='reg-001',
               task_tokens=None):
    """Seed a registration item with task tokens."""
    if task_tokens is None:
        task_tokens = {'registration': 'token-reg-abc'}
    table.put_item(Item={
        'requestId': request_id,
        'status': 'REGISTRATION_SUBMITTED',
        'registrationId': registration_id,
        'taskTokens': task_tokens,
    })


def _mock_sfn(app):
    """Attach a mocked Step Functions client."""
    mock = MagicMock()
    mock.send_task_success.return_value = {}
    mock.send_task_failure.return_value = {}
    app.sfn = mock
    return mock


def _make_event(registration_id, status, reg_type='US_TOLL_FREE_REGISTRATION'):
    """Build an EventBridge Registration Status Change event."""
    return {
        'detail': {
            'registrationDetails': {
                'registrationId': registration_id,
                'currentStatus': status,
                'registrationType': reg_type,
            }
        }
    }


# ── Tests ────────────────────────────────────────────────────────────────


@mock_aws
def test_success_status_triggers_send_task_success(aws_env):
    """COMPLETE status → SendTaskSuccess called."""
    table = _create_table()
    _seed_item(table, 'req-001', 'reg-001', {'registration': 'token-abc'})

    app = _load_event_router()
    sfn_mock = _mock_sfn(app)

    event = _make_event('reg-001', 'COMPLETE')
    result = app.handler(event, None)

    assert result['action'] == 'callback_sent'
    sfn_mock.send_task_success.assert_called_once()
    call_kwargs = sfn_mock.send_task_success.call_args.kwargs
    assert call_kwargs['taskToken'] == 'token-abc'


@mock_aws
def test_failure_status_triggers_send_task_failure(aws_env):
    """REQUIRES_UPDATES status → SendTaskFailure called."""
    table = _create_table()
    _seed_item(table, 'req-002', 'reg-002', {'registration': 'token-def'})

    app = _load_event_router()
    sfn_mock = _mock_sfn(app)

    event = _make_event('reg-002', 'REQUIRES_UPDATES')
    result = app.handler(event, None)

    assert result['action'] == 'callback_sent'
    sfn_mock.send_task_failure.assert_called_once()
    call_kwargs = sfn_mock.send_task_failure.call_args.kwargs
    assert call_kwargs['taskToken'] == 'token-def'
    assert call_kwargs['error'] == 'REQUIRES_UPDATES'


@mock_aws
def test_ignored_status_returns_without_action(aws_env):
    """REVIEWING status → no SFN callback, returns ignored."""
    table = _create_table()
    _seed_item(table, 'req-003', 'reg-003')

    app = _load_event_router()
    sfn_mock = _mock_sfn(app)

    event = _make_event('reg-003', 'REVIEWING')
    result = app.handler(event, None)

    assert result['action'] == 'ignored'
    sfn_mock.send_task_success.assert_not_called()
    sfn_mock.send_task_failure.assert_not_called()


@mock_aws
def test_unmatched_registration_returns_no_match(aws_env):
    """Unknown registrationId → no_match, no SFN callback."""
    _create_table()

    app = _load_event_router()
    sfn_mock = _mock_sfn(app)

    event = _make_event('reg-unknown', 'COMPLETE')
    result = app.handler(event, None)

    assert result['action'] == 'no_match'
    sfn_mock.send_task_success.assert_not_called()


@mock_aws
def test_missing_token_returns_no_token(aws_env):
    """Matched request but no task token → no_token."""
    table = _create_table()
    _seed_item(table, 'req-004', 'reg-004', task_tokens={})

    app = _load_event_router()
    sfn_mock = _mock_sfn(app)

    event = _make_event('reg-004', 'COMPLETE')
    result = app.handler(event, None)

    assert result['action'] == 'no_token'
    sfn_mock.send_task_success.assert_not_called()


@mock_aws
def test_human_intervention_token_preferred(aws_env):
    """When both tokens exist, human_intervention is used."""
    table = _create_table()
    _seed_item(table, 'req-005', 'reg-005', {
        'registration': 'token-reg',
        'human_intervention': 'token-human',
    })

    app = _load_event_router()
    sfn_mock = _mock_sfn(app)

    event = _make_event('reg-005', 'COMPLETE')
    result = app.handler(event, None)

    assert result['action'] == 'callback_sent'
    sfn_mock.send_task_success.assert_called_once()
    call_kwargs = sfn_mock.send_task_success.call_args.kwargs
    assert call_kwargs['taskToken'] == 'token-human'
