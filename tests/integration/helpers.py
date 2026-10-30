# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Shared helpers for toll-free registration integration tests.
"""
import json
import time

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


# ---------------------------------------------------------------------------
# CloudFormation helpers
# ---------------------------------------------------------------------------

def get_stack_outputs(stack_name, region='us-west-2'):
    """Fetch CloudFormation stack outputs as a dict."""
    cfn = boto3.client('cloudformation', region_name=region)
    resp = cfn.describe_stacks(StackName=stack_name)
    outputs = resp['Stacks'][0].get('Outputs', [])
    return {o['OutputKey']: o['OutputValue'] for o in outputs}


# ---------------------------------------------------------------------------
# API call wrappers
# ---------------------------------------------------------------------------

def _signed_post(url, body=None):
    """POST with a SigV4 signature. The API uses IAM auth on every route."""
    session = boto3.Session()
    region = url.split('.execute-api.')[1].split('.')[0]
    data = json.dumps(body) if body is not None else ''
    headers = {'Content-Type': 'application/json'}
    request = AWSRequest(method='POST', url=url, data=data, headers=headers)
    SigV4Auth(session.get_credentials(), 'execute-api', region).add_auth(request)
    return requests.post(url, data=data, headers=dict(request.headers), timeout=30)


def submit_registration(api_url, body=None):
    """POST /api/submit — submit a toll-free registration."""
    if body is None:
        body = build_test_payload()
    url = f'{api_url}/api/submit'
    resp = _signed_post(url, body)
    resp.raise_for_status()
    return resp.json()


def get_upload_url(api_url, body):
    """POST /api/upload-url — request a presigned upload URL."""
    url = f'{api_url}/api/upload-url'
    resp = _signed_post(url, body)
    resp.raise_for_status()
    return resp.json()


def resume_registration(api_url, request_id):
    """POST /api/resume/{requestId} — resume after human intervention."""
    url = f'{api_url}/api/resume/{request_id}'
    resp = _signed_post(url)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def get_dynamodb_item(table_name, request_id, region='us-west-2'):
    """Fetch a registration item from DynamoDB by requestId."""
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)
    resp = table.get_item(Key={'requestId': request_id})
    return resp.get('Item')


def wait_for_task_token(table_name, request_id, token_key,
                        timeout=60, poll_interval=3, region='us-west-2'):
    """Poll DynamoDB until a task token appears for the given key."""
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)
    deadline = time.time() + timeout

    while time.time() < deadline:
        resp = table.get_item(Key={'requestId': request_id})
        item = resp.get('Item', {})
        tokens = item.get('taskTokens', {})
        if token_key in tokens:
            return tokens[token_key]
        time.sleep(poll_interval)

    raise TimeoutError(
        f'Task token "{token_key}" not found for request {request_id} '
        f'within {timeout}s'
    )


# ---------------------------------------------------------------------------
# Step Functions helpers
# ---------------------------------------------------------------------------

def get_execution_status(sfn_arn, execution_name, region='us-west-2'):
    """Describe a Step Functions execution by ARN and execution name."""
    sfn = boto3.client('stepfunctions', region_name=region)
    execution_arn = f'{sfn_arn.replace(":stateMachine:", ":execution:")}:{execution_name}'
    resp = sfn.describe_execution(executionArn=execution_arn)
    return resp['status'], resp


def wait_for_execution_status(sfn_client, execution_arn, target_statuses,
                               timeout=120, poll_interval=5):
    """Poll a Step Functions execution until it reaches a target status."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = sfn_client.describe_execution(executionArn=execution_arn)
        status = resp['status']
        if status in target_statuses:
            return status, resp
        if status in ('FAILED', 'TIMED_OUT', 'ABORTED'):
            return status, resp
        time.sleep(poll_interval)

    raise TimeoutError(
        f'Execution {execution_arn} did not reach {target_statuses} '
        f'within {timeout}s'
    )


# ---------------------------------------------------------------------------
# Test payload builder
# ---------------------------------------------------------------------------

def build_test_payload():
    """Build a realistic toll-free registration test payload."""
    return {
        'companyFields': {
            'companyName': 'Test Company LLC',
            'website': 'https://example.com',
            'address1': '123 Test Street',
            'city': 'Seattle',
            'state': 'WA',
            'zipCode': '98101',
            'country': 'US',
            'businessType': 'PRIVATE_PROFIT',
            'companyIdNumber': '12-3456789',
            'companyIdType': 'EIN',
            'companyIdCountry': 'US',
        },
        'contactFields': {
            'firstName': 'Jane',
            'lastName': 'Doe',
            'supportEmail': 'jane.doe@example.com',
            'supportPhoneNumber': '+12065550142',
        },
        'useCaseFields': {
            'monthlyMessageVolume': '10,000',
            'useCaseCategory': 'ONE_TIME_PASSCODES',
            'useCaseDetails': 'Sending OTP codes for account verification',
            'privacyPolicyUrl': 'https://example.com/privacy',
            'termsAndConditionsUrl': 'https://example.com/terms',
            'optInType': 'VERBAL',
            'optInWorkflow': 'Users opt in during account creation by checking a consent checkbox.',
        },
        'messageSamples': {
            'messageSample1': 'Your verification code is 839274. This code expires in 10 minutes.',
            'messageSample2': 'Your login code is 482910. Do not share this code.',
        },
        'attachments': {},
        'phoneConfig': {
            'messageType': 'TRANSACTIONAL',
            'capabilities': ['SMS'],
        },
    }
