# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Unit tests for the Intake Lambda."""
import json
import re
import sys
import os
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws


def _load_intake():
    """Import the intake Lambda module, ensuring fresh module state."""
    lambda_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'lambda', 'intake'
    )
    if lambda_dir not in sys.path:
        sys.path.insert(0, lambda_dir)
    import importlib
    import app as intake_app
    importlib.reload(intake_app)
    return intake_app


def _valid_body():
    """Return a minimal valid request body dict."""
    return {
        'companyFields': {'companyName': 'Test Co', 'taxId': '12-3456789',
                          'website': 'https://example.com',
                          'address1': '123 Test Street', 'city': 'Seattle',
                          'state': 'WA', 'zipCode': '98101', 'country': 'US'},
        'contactFields': {'firstName': 'Jane', 'lastName': 'Doe',
                          'supportEmail': 'jane@example.com',
                          'supportPhoneNumber': '+12065550142'},
        'useCaseFields': {'privacyPolicyUrl': 'https://example.com/privacy',
                          'termsAndConditionsUrl': 'https://example.com/terms'},
    }


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
    table.meta.client.get_waiter('table_exists').wait(
        TableName='test-registrations'
    )
    return table


def _mock_sfn(app):
    """Attach a mocked Step Functions client to the intake app module."""
    mock = MagicMock()
    mock.start_execution.return_value = {
        'executionArn': 'arn:aws:states:us-east-1:000000000000:execution:test:reg-123',
        'startDate': '2026-04-17T00:00:00Z',
    }
    app.sfn = mock
    return mock


@mock_aws
def test_valid_submission_returns_200(aws_env):
    """Valid body with companyFields + contactFields returns 200 with requestId."""
    _create_table()
    app = _load_intake()
    sfn = _mock_sfn(app)

    event = {'body': json.dumps(_valid_body())}
    result = app.handler(event, None)

    assert result['statusCode'] == 200
    body = json.loads(result['body'])
    assert 'requestId' in body
    assert body['message'] == 'Registration workflow started'


@mock_aws
def test_missing_company_fields_returns_400(aws_env):
    """Body without companyFields returns 400."""
    _create_table()
    app = _load_intake()

    event = {'body': json.dumps({'contactFields': {'firstName': 'Jane'}})}
    result = app.handler(event, None)

    assert result['statusCode'] == 400
    body = json.loads(result['body'])
    assert 'companyFields' in body['error']


@mock_aws
def test_missing_contact_fields_returns_400(aws_env):
    """Body without contactFields returns 400."""
    _create_table()
    app = _load_intake()

    event = {'body': json.dumps({'companyFields': {'companyName': 'Test Co'}})}
    result = app.handler(event, None)

    assert result['statusCode'] == 400
    body = json.loads(result['body'])
    assert 'contactFields' in body['error']


@mock_aws
def test_non_dict_company_fields_returns_400(aws_env):
    """companyFields as a string returns 400."""
    _create_table()
    app = _load_intake()

    event = {'body': json.dumps({
        'companyFields': 'not-a-dict',
        'contactFields': {'firstName': 'Jane'},
    })}
    result = app.handler(event, None)

    assert result['statusCode'] == 400
    body = json.loads(result['body'])
    assert 'companyFields' in body['error']


def test_non_json_body_returns_400(aws_env):
    """Non-JSON body returns 400 with parse error."""
    app = _load_intake()

    event = {'body': 'this is not json!!!'}
    result = app.handler(event, None)

    assert result['statusCode'] == 400
    body = json.loads(result['body'])
    assert 'error' in body


@mock_aws
def test_dynamodb_write_creates_record(aws_env):
    """After valid submission, DynamoDB item exists with correct fields."""
    table = _create_table()
    app = _load_intake()
    sfn = _mock_sfn(app)

    payload = _valid_body()
    event = {'body': json.dumps(payload)}
    result = app.handler(event, None)

    assert result['statusCode'] == 200
    request_id = json.loads(result['body'])['requestId']

    # Verify the DynamoDB record
    item = table.get_item(Key={'requestId': request_id})['Item']
    assert item['status'] == 'SUBMITTED'
    assert item['companyFields']['companyName'] == 'Test Co'
    assert item['contactFields']['firstName'] == 'Jane'
    assert item['useCaseFields']['privacyPolicyUrl'] == 'https://example.com/privacy'
    assert item['useCaseFields']['termsAndConditionsUrl'] == 'https://example.com/terms'
    assert item['registrationId'] == '-'
    assert item['phoneNumberId'] == '-'
    assert item['taskTokens'] == {}

    # Verify Step Functions was started
    sfn.start_execution.assert_called_once()
    call_kwargs = sfn.start_execution.call_args.kwargs
    assert f'reg-{request_id}' == call_kwargs['name']


# Pattern from DescribeRegistrationFieldDefinitions for both URL fields
API_URL_PATTERN = re.compile(
    r'^(https?://)?(?=\w)([\w\-\.])*\w+\.([a-zA-Z]{2,63})([/\w-]*)*/?\??([^#\n\r]*)?#?([^\n\r]*)$'
)


@mock_aws
def test_missing_use_case_fields_returns_400(aws_env):
    """Body without useCaseFields returns 400."""
    _create_table()
    app = _load_intake()

    payload = _valid_body()
    del payload['useCaseFields']
    result = app.handler({'body': json.dumps(payload)}, None)

    assert result['statusCode'] == 400
    assert 'useCaseFields' in json.loads(result['body'])['error']


@mock_aws
def test_missing_url_fields_returns_400(aws_env):
    """useCaseFields without both URLs returns 400 naming each field."""
    _create_table()
    app = _load_intake()
    sfn = _mock_sfn(app)

    payload = _valid_body()
    payload['useCaseFields'] = {'useCaseCategory': 'ONE_TIME_PASSCODES'}
    result = app.handler({'body': json.dumps(payload)}, None)

    assert result['statusCode'] == 400
    error = json.loads(result['body'])['error']
    assert 'privacyPolicyUrl' in error
    assert 'termsAndConditionsUrl' in error
    sfn.start_execution.assert_not_called()


@mock_aws
@pytest.mark.parametrize('field', ['privacyPolicyUrl', 'termsAndConditionsUrl'])
@pytest.mark.parametrize('url', [
    'not a url',
    'example.com/privacy',
    'ftp://example.com/privacy',
    'HTTPS://example.com/privacy',
    'https://localhost/privacy',
    'https://-example.com/privacy',
    'https://example.com/pri vacy',
    'https://a.c',
    'https://example.com/' + 'a' * 481,
    12345678901234,
])
def test_invalid_url_returns_400(aws_env, field, url):
    """A URL field that is not an http or https URL of 12 to 500 chars returns 400."""
    _create_table()
    app = _load_intake()
    sfn = _mock_sfn(app)

    payload = _valid_body()
    payload['useCaseFields'][field] = url
    result = app.handler({'body': json.dumps(payload)}, None)

    assert result['statusCode'] == 400
    assert f'useCaseFields.{field}' in json.loads(result['body'])['error']
    sfn.start_execution.assert_not_called()


@mock_aws
@pytest.mark.parametrize('field', ['privacyPolicyUrl', 'termsAndConditionsUrl'])
@pytest.mark.parametrize('url', [
    'https://a.co',
    'http://example.co.uk/terms',
    'https://www.example.com/legal/privacy-policy?lang=en#sms',
    'https://example.com:8443/privacy',
    'https://example.com/' + 'a' * 480,
])
def test_valid_url_passes_intake_and_api_pattern(aws_env, field, url):
    """URLs that intake accepts also match the API pattern for the field."""
    _create_table()
    app = _load_intake()
    _mock_sfn(app)

    payload = _valid_body()
    payload['useCaseFields'][field] = url
    result = app.handler({'body': json.dumps(payload)}, None)

    assert result['statusCode'] == 200
    assert API_URL_PATTERN.match(url)
