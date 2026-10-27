# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Presigned URL Lambda - generates time-limited S3 PUT URLs
for direct browser-to-S3 file uploads (opt-in screenshots, etc.).
"""
import json
import os
import uuid

import boto3

s3 = boto3.client('s3')
BUCKET = os.environ['UPLOAD_BUCKET']
ALLOWED_TYPES = {'image/png', 'image/jpeg', 'application/pdf'}
URL_EXPIRY = 600  # 10 minutes


def handler(event, context):
    body = json.loads(event.get('body', '{}'))

    content_type = body.get('contentType', '')
    field_name = body.get('fieldName', '')
    request_id = body.get('requestId', str(uuid.uuid4()))

    if content_type not in ALLOWED_TYPES:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': f'Invalid file type: {content_type}. '
                         f'Must be one of: {", ".join(sorted(ALLOWED_TYPES))}.'
            }),
        }

    if not field_name:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'fieldName is required'}),
        }

    # Sanitize fieldName to prevent path traversal
    import re
    safe_field = re.sub(r'[^a-zA-Z0-9_-]', '', field_name)
    if not safe_field or safe_field != field_name:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'fieldName contains invalid characters. '
                         'Only alphanumeric, hyphens, and underscores are allowed.'
            }),
        }

    # Map content type to file extension
    ext = {
        'image/png': '.png',
        'image/jpeg': '.jpg',
        'application/pdf': '.pdf',
    }.get(content_type, '')
    s3_key = f'uploads/{request_id}/{safe_field}{ext}'

    # Generate presigned PUT URL
    url = s3.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': BUCKET,
            'Key': s3_key,
            'ContentType': content_type,
        },
        ExpiresIn=URL_EXPIRY,
    )

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'uploadUrl': url,
            's3Key': s3_key,
            'bucket': BUCKET,
            'expiresIn': URL_EXPIRY,
        }),
    }
