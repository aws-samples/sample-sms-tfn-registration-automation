# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Resume Lambda - human-in-the-loop endpoint.
After a rejection, the operator fixes the registration in the console
and calls POST /api/resume/{requestId} to resume the workflow.

Simplified from 10DLC: only one human_intervention token key
(vs. 10DLC's brand_human_intervention, vetting_human_intervention,
campaign_human_intervention).
"""
import json
import os

import boto3

dynamodb = boto3.resource('dynamodb')
sfn = boto3.client('stepfunctions')
table = dynamodb.Table(os.environ['REGISTRATIONS_TABLE'])


def handler(event, context):
    # Validate requestId path parameter
    request_id = (event.get('pathParameters') or {}).get('requestId')
    if not request_id:
        return _response(400, {'error': 'requestId is required'})

    # Look up the request
    resp = table.get_item(Key={'requestId': request_id})
    item = resp.get('Item')
    if not item:
        return _response(404, {'error': f'Request {request_id} not found'})

    task_tokens = item.get('taskTokens', {})

    # Find the human_intervention token
    task_token = task_tokens.get('human_intervention')
    if not task_token:
        return _response(400, {
            'error': 'No pending human intervention found for this request',
            'currentStatus': item.get('status'),
        })

    # Resume the Step Functions execution
    sfn.send_task_success(
        taskToken=task_token,
        output=json.dumps({
            'requestId': request_id,
            'resumedBy': 'human',
            'tokenKey': 'human_intervention',
        }),
    )

    # Clean up the used token and update status
    table.update_item(
        Key={'requestId': request_id},
        UpdateExpression='REMOVE taskTokens.#tk SET #s = :status, updatedAt = :now',
        ExpressionAttributeNames={
            '#tk': 'human_intervention',
            '#s': 'status',
        },
        ExpressionAttributeValues={
            ':status': 'RESUMED_FROM_HUMAN_INTERVENTION',
            ':now': _now(),
        },
    )

    return _response(200, {
        'message': f'Workflow resumed for request {request_id}',
        'resumedFrom': 'human_intervention',
    })


def _response(status_code, body):
    """Return an API Gateway-compatible response."""
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body),
    }


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
