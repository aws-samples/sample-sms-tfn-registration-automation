# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Shared fixtures for toll-free registration unit tests.
Sets up mocked AWS services and environment variables.
"""
import os
import pytest
import boto3
from moto import mock_aws


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Set environment variables that all Lambdas expect."""
    monkeypatch.setenv('REGISTRATIONS_TABLE', 'test-registrations')
    monkeypatch.setenv('UPLOAD_BUCKET', 'amzn-s3-demo-uploads')
    monkeypatch.setenv('STATE_MACHINE_ARN',
                       'arn:aws:states:us-east-1:000000000000:stateMachine:test-workflow')
    monkeypatch.setenv('NOTIFICATION_TOPIC_ARN',
                       'arn:aws:sns:us-east-1:000000000000:test-notifications')
    monkeypatch.setenv('DRY_RUN', 'false')
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_SECURITY_TOKEN', 'testing')
    monkeypatch.setenv('AWS_SESSION_TOKEN', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')


@pytest.fixture
def dynamodb_table():
    """Create a mocked DynamoDB table matching the SAM template schema."""
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='test-registrations',
            KeySchema=[{'AttributeName': 'requestId', 'KeyType': 'HASH'}],
            AttributeDefinitions=[
                {'AttributeName': 'requestId', 'AttributeType': 'S'},
                {'AttributeName': 'registrationId', 'AttributeType': 'S'},
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'registration-id-index',
                    'KeySchema': [
                        {'AttributeName': 'registrationId', 'KeyType': 'HASH'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                },
            ],
            BillingMode='PAY_PER_REQUEST',
        )
        table.meta.client.get_waiter('table_exists').wait(
            TableName='test-registrations'
        )
        yield table


@pytest.fixture
def s3_bucket():
    """Create a mocked S3 bucket."""
    with mock_aws():
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='amzn-s3-demo-uploads')
        yield s3


@pytest.fixture
def sns_topic(monkeypatch):
    """Create a mocked SNS topic and set the ARN env var."""
    with mock_aws():
        sns = boto3.client('sns', region_name='us-east-1')
        resp = sns.create_topic(Name='test-notifications')
        topic_arn = resp['TopicArn']
        monkeypatch.setenv('NOTIFICATION_TOPIC_ARN', topic_arn)
        yield sns, topic_arn


@pytest.fixture
def sample_registration_item():
    """A DynamoDB item representing a toll-free registration in progress."""
    return {
        'requestId': 'test-request-001',
        'status': 'REGISTRATION_SUBMITTED',
        'createdAt': '2026-04-17T00:00:00Z',
        'updatedAt': '2026-04-17T00:00:00Z',
        'companyFields': {
            'companyName': 'Test Company LLC',
            'taxId': '12-3456789',
            'address': '123 Test Street',
            'city': 'Seattle',
            'state': 'WA',
            'zipCode': '98101',
            'isoCountryCode': 'US',
        },
        'contactFields': {
            'firstName': 'Jane',
            'lastName': 'Doe',
            'email': 'jane@example.com',
            'phoneNumber': '+12065550142',
        },
        'useCaseFields': {
            'monthlyVolume': '10000',
            'useCase': 'TWO_FACTOR_AUTHENTICATION',
            'useCaseDescription': 'Sending OTP codes',
            'optInType': 'VERBAL',
            'optInWorkflow': 'Customer calls in and opts in verbally',
        },
        'messageSamples': {
            'messageSample1': 'Your code is 123456.',
            'messageSample2': 'Your verification code is 654321.',
        },
        'attachments': {},
        'phoneConfig': {'messageType': 'TRANSACTIONAL', 'capabilities': ['SMS']},
        'registrationId': 'reg-tf-001',
        'phoneNumberId': 'phone-001',
        'phoneNumber': '+18885550142',
        'phoneNumberArn': 'arn:aws:sms-voice:us-east-1:000000000000:phone-number/phone-001',
        'taskTokens': {
            'registration': 'test-task-token-registration',
        },
    }
