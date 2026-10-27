# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Synthetic EventBridge Event Simulator for Toll-Free Registration

Instead of publishing to EventBridge (which blocks reserved 'aws.*' sources),
this simulator directly calls SendTaskSuccess/SendTaskFailure on the Step
Functions task tokens stored in DynamoDB. This exercises the same resume logic
that the Event Router Lambda uses, just bypassing the EventBridge -> Lambda hop.

For testing the Event Router Lambda itself, use the SAM local invoke fixtures
in tests/events/.

Usage:
    from event_simulator import EventSimulator

    sim = EventSimulator(region='us-west-2', table_name='my-table')
    sim.inject_approval_event(request_id='req-abc123')
    sim.inject_rejection_event(request_id='req-xyz789')
"""
import json
import time

import boto3


class EventSimulator:
    """Drives Step Functions workflow by directly calling SFN callbacks."""

    def __init__(self, region='us-west-2', table_name=None):
        self.sfn = boto3.client('stepfunctions', region_name=region)
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        self.table = self.dynamodb.Table(table_name) if table_name else None
        self.region = region

    def set_table(self, table_name):
        """Set or change the DynamoDB table."""
        self.table = self.dynamodb.Table(table_name)

    def inject_approval_event(self, request_id, registration_id='synthetic-tf-reg'):
        """
        Simulate an EventBridge approval (COMPLETE status) by calling
        SendTaskSuccess on the stored task token.

        Prefers the 'human_intervention' token if it exists, otherwise
        uses the 'registration' token — matching Event Router logic.
        """
        token_key = self._pick_token_key(request_id)
        task_token = self._get_token(request_id, token_key)
        self.sfn.send_task_success(
            taskToken=task_token,
            output=json.dumps({
                'registrationId': registration_id,
                'status': 'COMPLETE',
            }),
        )
        print(f'  OK SendTaskSuccess for "{token_key}" (request={request_id})')

    def inject_rejection_event(self, request_id, error='REQUIRES_UPDATES'):
        """
        Simulate an EventBridge rejection (REQUIRES_UPDATES status) by
        calling SendTaskFailure on the stored task token.
        """
        token_key = self._pick_token_key(request_id)
        task_token = self._get_token(request_id, token_key)
        self.sfn.send_task_failure(
            taskToken=task_token,
            error=error,
            cause=f'Synthetic test: {error}',
        )
        print(f'  OK SendTaskFailure for "{token_key}" error={error} (request={request_id})')

    # ---- Internal ---------------------------------------------------------

    def _pick_token_key(self, request_id):
        """Determine which token key to use, matching Event Router logic."""
        resp = self.table.get_item(Key={'requestId': request_id})
        tokens = resp.get('Item', {}).get('taskTokens', {})
        if 'human_intervention' in tokens:
            return 'human_intervention'
        return 'registration'

    def _get_token(self, request_id, token_key, timeout=60, poll_interval=3):
        """Poll DynamoDB until the task token appears."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = self.table.get_item(Key={'requestId': request_id})
            item = resp.get('Item', {})
            tokens = item.get('taskTokens', {})
            if token_key in tokens:
                return tokens[token_key]
            time.sleep(poll_interval)
        raise TimeoutError(
            f'Task token "{token_key}" not found for {request_id} within {timeout}s'
        )
