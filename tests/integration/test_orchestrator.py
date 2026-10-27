# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#!/usr/bin/env python3
"""
Toll-Free Registration Automation — Synthetic Integration Test Orchestrator

Drives the full Step Functions workflow by submitting a registration and then
using the EventSimulator to simulate approval/rejection events. The deployed
stack MUST have DRY_RUN=true so no real EUM SMS API calls are made.

Usage:
    python test_orchestrator.py --stack-name my-tfn-stack --scenario happy-path
    python test_orchestrator.py --stack-name my-tfn-stack --scenario all
    python test_orchestrator.py --stack-name my-tfn-stack --scenario rejection --region us-west-2
"""
import argparse
import sys
import time

import boto3

from event_simulator import EventSimulator
from helpers import (
    build_test_payload,
    get_dynamodb_item,
    get_stack_outputs,
    resume_registration,
    submit_registration,
    wait_for_execution_status,
    wait_for_task_token,
)

# Timeouts (seconds)
WAIT_STATE_TIMEOUT = 90
EVENT_PROCESSING_WAIT = 10


class TestOrchestrator:
    """Orchestrates synthetic end-to-end tests against a deployed stack."""

    def __init__(self, stack_name, region='us-west-2'):
        self.stack_name = stack_name
        self.region = region
        self.sfn = boto3.client('stepfunctions', region_name=region)

        outputs = get_stack_outputs(stack_name, region)
        self.api_endpoint = outputs['ApiEndpoint']
        self.table_name = f'{stack_name}-registrations'
        self.state_machine_arn = outputs['StateMachineArn']

        self.simulator = EventSimulator(region=region, table_name=self.table_name)
        self.results = []

    def run_scenario(self, scenario):
        """Run a named test scenario."""
        scenarios = {
            'happy-path': self.test_happy_path,
            'rejection': self.test_rejection_and_resume,
        }

        if scenario == 'all':
            for name, fn in scenarios.items():
                self._run_one(name, fn)
        elif scenario in scenarios:
            self._run_one(scenario, scenarios[scenario])
        else:
            print(f'Unknown scenario: {scenario}')
            print(f'Available: {", ".join(list(scenarios.keys()) + ["all"])}')
            sys.exit(1)

        self._print_summary()

    def _run_one(self, name, fn):
        print(f'\n{"=" * 60}')
        print(f'  SCENARIO: {name}')
        print(f'{"=" * 60}\n')
        try:
            fn()
            self.results.append((name, 'PASSED', None))
            print(f'\n  [PASS] {name}\n')
        except Exception as e:
            self.results.append((name, 'FAILED', str(e)))
            print(f'\n  [FAIL] {name} — {e}\n')

    def _print_summary(self):
        print(f'\n{"=" * 60}')
        print('  TEST SUMMARY')
        print(f'{"=" * 60}')
        passed = sum(1 for _, s, _ in self.results if s == 'PASSED')
        total = len(self.results)
        for name, status, error in self.results:
            icon = '[PASS]' if status == 'PASSED' else '[FAIL]'
            line = f'  {icon} {name}'
            if error:
                line += f' — {error}'
            print(line)
        print(f'\n  {passed}/{total} passed\n')

    # ---- Test Scenarios --------------------------------------------------

    def test_happy_path(self):
        """Submit → verify DDB → simulate approval → verify completion."""
        print('Step 1: Submitting registration...')
        result = submit_registration(self.api_endpoint, build_test_payload())
        request_id = result['requestId']
        print(f'  Request ID: {request_id}')

        print('\nStep 2: Verifying DynamoDB record...')
        item = get_dynamodb_item(self.table_name, request_id, self.region)
        assert item is not None, 'DynamoDB item should exist'
        assert item['status'] in ('SUBMITTED', 'PHONE_PROVISIONED', 'REGISTRATION_SUBMITTED'), \
            f'Unexpected status: {item["status"]}'
        print(f'  OK Status: {item["status"]}')

        print('\nStep 3: Waiting for registration task token...')
        wait_for_task_token(
            self.table_name, request_id, 'registration',
            timeout=WAIT_STATE_TIMEOUT, region=self.region,
        )
        print('  OK Registration task token stored')

        print('\nStep 4: Simulating approval event...')
        self.simulator.inject_approval_event(request_id)
        time.sleep(EVENT_PROCESSING_WAIT)

        print('\nStep 5: Verifying workflow completion...')
        item = self._wait_for_final_status(request_id, timeout=60)
        print(f'  OK Phone Number ID: {item.get("phoneNumberId", "N/A")}')
        print(f'  OK Final status: {item["status"]}')

    def test_rejection_and_resume(self):
        """Submit → simulate rejection → verify notification → resume → verify completion."""
        print('Step 1: Submitting registration...')
        result = submit_registration(self.api_endpoint, build_test_payload())
        request_id = result['requestId']
        print(f'  Request ID: {request_id}')

        print('\nStep 2: Waiting for registration task token...')
        wait_for_task_token(
            self.table_name, request_id, 'registration',
            timeout=WAIT_STATE_TIMEOUT, region=self.region,
        )
        print('  OK Registration task token stored')

        print('\nStep 3: Simulating rejection event...')
        self.simulator.inject_rejection_event(request_id)
        time.sleep(EVENT_PROCESSING_WAIT)

        print('\nStep 4: Waiting for human_intervention task token...')
        wait_for_task_token(
            self.table_name, request_id, 'human_intervention',
            timeout=WAIT_STATE_TIMEOUT, region=self.region,
        )
        print('  OK Workflow paused for human intervention')

        print('\nStep 5: Resuming via /api/resume endpoint...')
        resume_result = resume_registration(self.api_endpoint, request_id)
        print(f'  OK {resume_result.get("message", "Resumed")}')
        time.sleep(EVENT_PROCESSING_WAIT)

        print('\nStep 6: Verifying workflow completion...')
        item = self._wait_for_final_status(request_id, timeout=60)
        print(f'  OK Final status: {item["status"]}')

    # ---- Helpers ---------------------------------------------------------

    def _wait_for_final_status(self, request_id, timeout=60):
        """Wait for the Step Functions execution to succeed, then return the DynamoDB record."""
        execution_arn = (
            f'{self.state_machine_arn.replace(":stateMachine:", ":execution:")}:reg-{request_id}'
        )
        status, _ = wait_for_execution_status(
            self.sfn, execution_arn, ('SUCCEEDED',), timeout=timeout,
        )
        assert status == 'SUCCEEDED', f'Execution ended as {status}, expected SUCCEEDED'
        print(f'  OK Execution status: {status}')
        return get_dynamodb_item(self.table_name, request_id, self.region)


def main():
    parser = argparse.ArgumentParser(
        description='Toll-Free Registration Automation — Synthetic Integration Tests',
    )
    parser.add_argument('--stack-name', required=True, help='CloudFormation stack name')
    parser.add_argument(
        '--scenario', required=True,
        help='Test scenario: happy-path, rejection, all',
    )
    parser.add_argument('--region', default='us-west-2', help='AWS region (default: us-west-2, matches samconfig.toml)')
    args = parser.parse_args()

    orchestrator = TestOrchestrator(args.stack_name, args.region)
    orchestrator.run_scenario(args.scenario)


if __name__ == '__main__':
    main()
