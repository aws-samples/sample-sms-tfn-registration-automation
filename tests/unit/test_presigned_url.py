# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Unit tests for the Presigned URL Lambda."""
import json
import sys
import os

import boto3
import pytest
from moto import mock_aws


def _load_presigned():
    """Import the presigned_url Lambda module, ensuring fresh module state."""
    lambda_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'lambda', 'presigned_url'
    )
    if lambda_dir not in sys.path:
        sys.path.insert(0, lambda_dir)
    import importlib
    import app as presigned_app
    importlib.reload(presigned_app)
    return presigned_app


@mock_aws
def test_valid_request_returns_200(aws_env):
    """Valid contentType + fieldName returns 200 with upload details."""
    s3 = boto3.client('s3', region_name='us-east-1')
    s3.create_bucket(Bucket='amzn-s3-demo-uploads')

    app = _load_presigned()

    event = {
        'body': json.dumps({
            'contentType': 'image/png',
            'fieldName': 'optInScreenshot',
            'requestId': 'req-001',
        })
    }
    result = app.handler(event, None)

    assert result['statusCode'] == 200
    body = json.loads(result['body'])
    assert 'uploadUrl' in body
    assert body['uploadUrl']  # non-empty
    assert 's3Key' in body
    assert body['bucket'] == 'amzn-s3-demo-uploads'
    assert body['expiresIn'] == 600


@mock_aws
def test_invalid_content_type_returns_400(aws_env):
    """contentType not in allowed set returns 400."""
    app = _load_presigned()

    event = {
        'body': json.dumps({
            'contentType': 'text/html',
            'fieldName': 'optInScreenshot',
        })
    }
    result = app.handler(event, None)

    assert result['statusCode'] == 400
    body = json.loads(result['body'])
    assert 'Invalid file type' in body['error']


@mock_aws
def test_missing_field_name_returns_400(aws_env):
    """No fieldName returns 400."""
    app = _load_presigned()

    event = {
        'body': json.dumps({
            'contentType': 'image/png',
        })
    }
    result = app.handler(event, None)

    assert result['statusCode'] == 400
    body = json.loads(result['body'])
    assert 'fieldName is required' in body['error']


@mock_aws
def test_s3_key_format(aws_env):
    """s3Key matches uploads/{requestId}/{fieldName}{ext} pattern."""
    s3 = boto3.client('s3', region_name='us-east-1')
    s3.create_bucket(Bucket='amzn-s3-demo-uploads')

    app = _load_presigned()

    test_cases = [
        ('image/png', '.png'),
        ('image/jpeg', '.jpg'),
        ('application/pdf', '.pdf'),
    ]

    for content_type, expected_ext in test_cases:
        event = {
            'body': json.dumps({
                'contentType': content_type,
                'fieldName': 'testDoc',
                'requestId': 'req-format-test',
            })
        }
        result = app.handler(event, None)

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        expected_key = f'uploads/req-format-test/testDoc{expected_ext}'
        assert body['s3Key'] == expected_key, (
            f'Expected {expected_key}, got {body["s3Key"]} '
            f'for content type {content_type}'
        )
