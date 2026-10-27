# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Unit tests for the dry_run shared module."""
import sys
import os

import pytest


def _load_dry_run():
    """Import the dry_run module from the shared directory."""
    shared_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'lambda', 'shared'
    )
    if shared_dir not in sys.path:
        sys.path.insert(0, shared_dir)
    import importlib
    import dry_run
    importlib.reload(dry_run)
    return dry_run


# ── Tests ────────────────────────────────────────────────────────────────


def test_fake_phone_number_returns_toll_free(aws_env):
    """fake_phone_number returns NumberType TOLL_FREE."""
    dr = _load_dry_run()
    result = dr.fake_phone_number()
    assert result['NumberType'] == 'TOLL_FREE'


def test_fake_phone_number_returns_toll_free_number(aws_env):
    """fake_phone_number returns a phone number starting with +1800 or +1888."""
    dr = _load_dry_run()
    result = dr.fake_phone_number()
    phone = result['PhoneNumber']
    assert phone.startswith('+1800') or phone.startswith('+1888'), (
        f'Expected toll-free number (+1800 or +1888), got {phone}'
    )


def test_is_dry_run_true(aws_env, monkeypatch):
    """DRY_RUN=true → is_dry_run() returns True."""
    monkeypatch.setenv('DRY_RUN', 'true')
    dr = _load_dry_run()
    assert dr.is_dry_run() is True


def test_is_dry_run_false(aws_env, monkeypatch):
    """DRY_RUN=false → is_dry_run() returns False."""
    monkeypatch.setenv('DRY_RUN', 'false')
    dr = _load_dry_run()
    assert dr.is_dry_run() is False


def test_fake_create_registration_structure(aws_env):
    """fake_create_registration returns valid dict with expected keys."""
    dr = _load_dry_run()
    result = dr.fake_create_registration('US_TOLL_FREE_REGISTRATION')

    assert 'RegistrationId' in result
    assert result['RegistrationId']  # non-empty
    assert 'RegistrationType' in result
    assert result['RegistrationType'] == 'US_TOLL_FREE_REGISTRATION'
    assert 'RegistrationArn' in result
    assert 'RegistrationStatus' in result
    assert 'CurrentVersionNumber' in result
