# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Event Router Lambda - receives Amazon EventBridge Registration Status Change events
for US_TOLL_FREE_REGISTRATION type, looks up the task token in Amazon DynamoDB,
and calls SendTaskSuccess or SendTaskFailure to resume the workflow.

Simplified from 10DLC: only one registration type and one GSI to query.
"""
import json
import os

import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
sfn = boto3.client('stepfunctions')
table = dynamodb.Table(os.environ['REGISTRATIONS_TABLE'])

# Statuses that mean "approved / done"
SUCCESS_STATUSES = {'COMPLETE', 'PROVISIONING'}
# Statuses that mean "needs human intervention"
FAILURE_STATUSES = {'REQUIRES_UPDATES', 'REQUIRES_AUTHENTICATION', 'CLOSED', 'DELETED'}
# Statuses we ignore (still in progress)
IGNORE_STATUSES = {'CREATED', 'SUBMITTED', 'REVIEWING'}


def handler(event, context):
    detail = event.get('detail', {})
    reg_details = detail.get('registrationDetails', {})
    registration_id = reg_details.get('registrationId', '')
    current_status = reg_details.get('currentStatus', '')
    reg_type = reg_details.get('registrationType', '')

    print(f'Event: regId={registration_id}, status={current_status}, type={reg_type}')

    # Only handle toll-free registrations
    if reg_type != 'US_TOLL_FREE_REGISTRATION':
        print(f'Ignoring non-toll-free registration type: {reg_type}')
        return {'action': 'ignored', 'reason': 'wrong_type'}

    # Ignore in-progress statuses
    if current_status in IGNORE_STATUSES:
        print(f'Ignoring status: {current_status}')
        return {'action': 'ignored'}

    # Look up the request by registration ID using the GSI
    item = _find_by_reg_id(registration_id)
    if not item:
        print(f'No matching request found for registration {registration_id}')
        return {'action': 'no_match'}

    request_id = item['requestId']
    task_tokens = item.get('taskTokens', {})

    # Token key selection: prefer human_intervention if it exists, otherwise use registration
    token_key = _get_token_key(task_tokens)
    task_token = task_tokens.get(token_key)

    if not task_token:
        print(f'No task token found for key: {token_key}')
        return {'action': 'no_token'}

    # Update status in DynamoDB
    table.update_item(
        Key={'requestId': request_id},
        UpdateExpression='SET #s = :status, updatedAt = :now',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':status': f'REGISTRATION_{current_status}',
            ':now': _now(),
        },
    )

    # Send callback to Step Functions
    if current_status in SUCCESS_STATUSES:
        sfn.send_task_success(
            taskToken=task_token,
            output=json.dumps({
                'registrationId': registration_id,
                'status': current_status,
            }),
        )
        print(f'SendTaskSuccess for {token_key}')
    elif current_status in FAILURE_STATUSES:
        sfn.send_task_failure(
            taskToken=task_token,
            error=current_status,
            cause=f'Registration {registration_id} status: {current_status}',
        )
        print(f'SendTaskFailure for {token_key}: {current_status}')

    return {'action': 'callback_sent', 'status': current_status}


def _find_by_reg_id(registration_id):
    """Look up a request by registrationId using the GSI."""
    resp = table.query(
        IndexName='registration-id-index',
        KeyConditionExpression=Key('registrationId').eq(registration_id),
    )
    if resp['Items']:
        return resp['Items'][0]
    return None


def _get_token_key(task_tokens):
    """Determine which task token key to use.

    Prefer human_intervention (indicating a rejection-resume cycle)
    over the default registration token.
    """
    if 'human_intervention' in task_tokens:
        return 'human_intervention'
    return 'registration'


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
