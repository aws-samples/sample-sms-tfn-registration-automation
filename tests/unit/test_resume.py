# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Unit tests for the Resume Lambda."""
import json
import sys
import os
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws


def _load_resume():
    """Import the resume Lambda module, ensuring fresh module state."""
    lambda_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'lambda', 'resume'
    )
    if lambda_dir not in sys.path:
        sys.path.insert(0, lambda_dir)
    import importlib
    import app as resume_app
    importlib.reload(resume_app)
    return resume_app


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


def _mock_sfn(app):
    """Attach a mocked Step Functions client."""
    mock = MagicMock()
    mock.send_task_success.return_value = {}
    app.sfn = mock
    return mock


# ── Tests ────────────────────────────────────────────────────────────────


@mock_aws
def test_valid_resume_returns_200(aws_env):
    """Request with human_intervention token → 200, SendTaskSuccess called."""
    table = _create_table()
    table.put_item(Item={
        'requestId': 'req-resume-001',
        'status': 'REGISTRATION_REQUIRES_UPDATES',
        'registrationId': 'reg-001',
        'taskTokens': {'human_intervention': 'token-human-abc'},
    })

    app = _load_resume()
    sfn_mock = _mock_sfn(app)

    event = {'pathParameters': {'requestId': 'req-resume-001'}}
    result = app.handler(event, None)

    assert result['statusCode'] == 200
    body = json.loads(result['body'])
    assert 'resumed' in body['message'].lower() or 'Workflow resumed' in body['message']

    sfn_mock.send_task_success.assert_called_once()
    call_kwargs = sfn_mock.send_task_success.call_args.kwargs
    assert call_kwargs['taskToken'] == 'token-human-abc'


@mock_aws
def test_missing_request_returns_404(aws_env):
    """Unknown requestId → 404."""
    _create_table()

    app = _load_resume()
    _mock_sfn(app)

    event = {'pathParameters': {'requestId': 'req-nonexistent'}}
    result = app.handler(event, None)

    assert result['statusCode'] == 404
    body = json.loads(result['body'])
    assert 'not found' in body['error'].lower()


@mock_aws
def test_no_token_returns_400(aws_env):
    """Request exists but no human_intervention token → 400."""
    table = _create_table()
    table.put_item(Item={
        'requestId': 'req-no-token',
        'status': 'REGISTRATION_SUBMITTED',
        'registrationId': 'reg-002',
        'taskTokens': {},
    })

    app = _load_resume()
    _mock_sfn(app)

    event = {'pathParameters': {'requestId': 'req-no-token'}}
    result = app.handler(event, None)

    assert result['statusCode'] == 400
    body = json.loads(result['body'])
    assert 'human intervention' in body['error'].lower() or 'No pending' in body['error']


def test_missing_path_parameter_returns_400(aws_env):
    """No requestId in pathParameters → 400."""
    app = _load_resume()

    event = {'pathParameters': {}}
    result = app.handler(event, None)

    assert result['statusCode'] == 400
    body = json.loads(result['body'])
    assert 'requestId' in body['error']
