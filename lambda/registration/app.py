# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Registration Lambda - handles the full toll-free registration lifecycle:
  1. request_phone_number - Request a TOLL_FREE phone number
  2. create_associate_populate_submit - Create registration, associate phone,
     populate all fields, and submit
  3. store_task_token - Store task token for EventBridge callback

Key difference from 10DLC: toll-free uses ASSOCIATE_BEFORE_SUBMIT, meaning
the phone number must be purchased and associated BEFORE submitting the
registration. This is the opposite of 10DLC campaigns which use
ASSOCIATE_AFTER_COMPLETE.

Field sections:
  - companyInfo: companyName, taxId, address, city, state, zipCode, isoCountryCode
  - contactInfo: firstName, lastName, email, phoneNumber
  - messagingUseCase: monthlyMessageVolume, useCaseCategory, useCaseDetails,
    privacyPolicyUrl, termsAndConditionsUrl, optInType, optInDescription, optInImage
  - messageSamples: messageSample1-5
"""
import os

import boto3

from dry_run import is_dry_run, fake_phone_number, fake_create_registration

dynamodb = boto3.resource('dynamodb')
sms = boto3.client('pinpoint-sms-voice-v2')
table = dynamodb.Table(os.environ['REGISTRATIONS_TABLE'])
BUCKET = os.environ['UPLOAD_BUCKET']

# ── Field mappings: form key → (FieldPath, value_type) ──────────────────

COMPANY_INFO_FIELDS = {
    'companyName':     ('companyInfo.companyName', 'text'),
    'website':         ('companyInfo.website', 'text'),
    'address1':        ('companyInfo.address1', 'text'),
    'address2':        ('companyInfo.address2', 'text'),
    'city':            ('companyInfo.city', 'text'),
    'state':           ('companyInfo.state', 'text'),
    'zipCode':         ('companyInfo.zipCode', 'text'),
    'country':         ('companyInfo.isoCountryCode', 'text'),
    'businessType':    ('companyInfo.businessType', 'select'),
    'companyIdNumber': ('companyInfo.taxId', 'text'),
    'companyIdType':   ('companyInfo.taxIdAuthority', 'select'),
    'companyIdCountry':('companyInfo.taxIdCountry', 'text'),
}

CONTACT_INFO_FIELDS = {
    'firstName':          ('contactInfo.firstName', 'text'),
    'lastName':           ('contactInfo.lastName', 'text'),
    'supportEmail':       ('contactInfo.supportEmail', 'text'),
    'supportPhoneNumber': ('contactInfo.supportPhoneNumber', 'text'),
}

USE_CASE_FIELDS = {
    'monthlyMessageVolume':  ('messagingUseCase.monthlyMessageVolume', 'select'),
    'useCaseCategory':       ('messagingUseCase.useCaseCategory', 'select'),
    'useCaseDetails':        ('messagingUseCase.useCaseDetails', 'text'),
    'privacyPolicyUrl':      ('messagingUseCase.privacyPolicyUrl', 'text'),
    'termsAndConditionsUrl': ('messagingUseCase.termsAndConditionsUrl', 'text'),
    'optInType':             ('messagingUseCase.optInType', 'select'),
    'optInWorkflow':         ('messagingUseCase.optInDescription', 'text'),
}

MESSAGE_SAMPLE_FIELDS = [
    ('messageSample1', 'messageSamples.messageSample1'),
    ('messageSample2', 'messageSamples.messageSample2'),
    ('messageSample3', 'messageSamples.messageSample3'),
]

# Attachment fields: form key → FieldPath
ATTACHMENT_FIELDS = {
    'optInScreenshot': 'messagingUseCase.optInImage',
}


def handler(event, context):
    """Dispatch on the `action` field in the event payload."""
    payload = event.get('Payload', event)
    request_id = payload['requestId']
    action = payload.get('action')

    if action == 'request_phone_number':
        return request_phone_number(request_id)

    if action == 'create_associate_populate_submit':
        return create_associate_populate_submit(request_id)

    if action == 'store_task_token':
        return store_task_token(request_id, payload)

    return {'error': f'Unknown action: {action}'}


# ── Action: request_phone_number ─────────────────────────────────────────

def request_phone_number(request_id):
    """Request a TOLL_FREE phone number via EUM SMS API."""
    dry = is_dry_run()

    if not dry:
        resp = sms.request_phone_number(
            IsoCountryCode='US',
            MessageType='TRANSACTIONAL',
            NumberCapabilities=['SMS'],
            NumberType='TOLL_FREE',
        )
    else:
        resp = fake_phone_number()

    phone_number_id = resp['PhoneNumberId']
    phone_number = resp.get('PhoneNumber', '')
    phone_number_arn = resp.get('PhoneNumberArn', '')

    # Update DynamoDB with phone details
    table.update_item(
        Key={'requestId': request_id},
        UpdateExpression=(
            'SET phoneNumberId = :pid, phoneNumber = :pn, '
            'phoneNumberArn = :arn, #s = :status, updatedAt = :now'
        ),
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':pid': phone_number_id,
            ':pn': phone_number,
            ':arn': phone_number_arn,
            ':status': 'PHONE_PROVISIONED',
            ':now': _now(),
        },
    )

    return {
        'phoneNumberId': phone_number_id,
        'phoneNumber': phone_number,
        'phoneNumberArn': phone_number_arn,
        'status': 'PHONE_PROVISIONED',
    }


# ── Action: create_associate_populate_submit ─────────────────────────────

def create_associate_populate_submit(request_id):
    """Create registration, associate phone, populate fields, submit."""
    dry = is_dry_run()

    # Fetch the full request from DynamoDB
    item = table.get_item(Key={'requestId': request_id})['Item']
    phone_number_id = item['phoneNumberId']
    company_fields = item.get('companyFields', {})
    contact_fields = item.get('contactFields', {})
    use_case_fields = item.get('useCaseFields', {})
    message_samples = item.get('messageSamples', {})
    attachments = item.get('attachments', {})

    # 1. Create the toll-free registration
    if not dry:
        resp = sms.create_registration(
            RegistrationType='US_TOLL_FREE_REGISTRATION',
            Tags=[{'Key': 'Name', 'Value': f'{request_id}-TollFree'}],
        )
    else:
        resp = fake_create_registration('US_TOLL_FREE_REGISTRATION')
    reg_id = resp['RegistrationId']

    if not dry:
        # 2. Associate phone number BEFORE submit (ASSOCIATE_BEFORE_SUBMIT)
        sms.create_registration_association(
            RegistrationId=reg_id,
            ResourceId=phone_number_id,
        )

        # 3. Populate companyInfo fields
        for form_key, (field_path, val_type) in COMPANY_INFO_FIELDS.items():
            value = company_fields.get(form_key)
            if value:
                _put_field(reg_id, field_path, value, val_type)

        # 4. Populate contactInfo fields
        for form_key, (field_path, val_type) in CONTACT_INFO_FIELDS.items():
            value = contact_fields.get(form_key)
            if value:
                _put_field(reg_id, field_path, value, val_type)

        # 5. Populate messagingUseCase fields
        for form_key, (field_path, val_type) in USE_CASE_FIELDS.items():
            value = use_case_fields.get(form_key)
            if value:
                _put_field(reg_id, field_path, value, val_type)

        # 6. Populate message samples
        for form_key, field_path in MESSAGE_SAMPLE_FIELDS:
            value = message_samples.get(form_key)
            if value:
                _put_field(reg_id, field_path, value, 'text')

        # 7. Upload attachments (opt-in screenshots from S3)
        for form_key, field_path in ATTACHMENT_FIELDS.items():
            s3_key = attachments.get(form_key)
            if s3_key:
                s3_url = f's3://{BUCKET}/{s3_key}'
                attach_resp = sms.create_registration_attachment(
                    AttachmentUrl=s3_url,
                )
                attach_id = attach_resp['RegistrationAttachmentId']
                # Wait for attachment to become active before assigning
                import time
                for _ in range(30):  # up to 30 seconds
                    desc = sms.describe_registration_attachments(
                        RegistrationAttachmentIds=[attach_id],
                    )
                    status = desc['RegistrationAttachments'][0]['AttachmentStatus']
                    if status == 'UPLOAD_COMPLETE':
                        break
                    time.sleep(1)
                if status != 'UPLOAD_COMPLETE':
                    raise RuntimeError(
                        f'Attachment {attach_id} is {status} after 30s, not UPLOAD_COMPLETE'
                    )
                sms.put_registration_field_value(
                    RegistrationId=reg_id,
                    FieldPath=field_path,
                    RegistrationAttachmentId=attach_id,
                )

        # 8. Submit the registration version
        sms.submit_registration_version(RegistrationId=reg_id)

    # Update DynamoDB with registration ID and status
    table.update_item(
        Key={'requestId': request_id},
        UpdateExpression='SET registrationId = :rid, #s = :status, updatedAt = :now',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':rid': reg_id,
            ':status': 'REGISTRATION_SUBMITTED',
            ':now': _now(),
        },
    )

    return {'registrationId': reg_id, 'status': 'REGISTRATION_SUBMITTED'}


# ── Action: store_task_token ─────────────────────────────────────────────

def store_task_token(request_id, payload):
    """Store Step Functions task token in DynamoDB for EventBridge callback.

    This Lambda is invoked with .waitForTaskToken — it does NOT return a value.
    Step Functions will pause until SendTaskSuccess/Failure is called.
    """
    task_token = payload['taskToken']
    waiting_for = payload['waitingFor']

    table.update_item(
        Key={'requestId': request_id},
        UpdateExpression='SET taskTokens.#wf = :token, updatedAt = :now',
        ExpressionAttributeNames={'#wf': waiting_for},
        ExpressionAttributeValues={
            ':token': task_token,
            ':now': _now(),
        },
    )
    # Do NOT return — waitForTaskToken pattern


# ── Helpers ──────────────────────────────────────────────────────────────

def _put_field(reg_id, field_path, value, val_type):
    """Set a single registration field value."""
    params = {'RegistrationId': reg_id, 'FieldPath': field_path}
    if val_type == 'select':
        params['SelectChoices'] = [value] if isinstance(value, str) else value
    else:
        params['TextValue'] = value
    sms.put_registration_field_value(**params)


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
