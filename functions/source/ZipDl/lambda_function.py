#  Copyright 2016 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.
#  This file is licensed to you under the AWS Customer Agreement (the "License").
#  You may not use this file except in compliance with the License.
#  A copy of the License is located at http://aws.amazon.com/agreement/ .
#  This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied.
#  See the License for the specific language governing permissions and limitations under the License.

import boto3
from botocore.vendored import requests
import logging
import base64
import os
import shutil
from zipfile import ZipFile
from cStringIO import StringIO

# Set to False to allow self-signed/invalid ssl certificates
verify = False

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.handlers[0].setFormatter(logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s'))
logging.getLogger('boto3').setLevel(logging.ERROR)
logging.getLogger('botocore').setLevel(logging.ERROR)
params = None
s3_client = boto3.client('s3')


def get_members(zip):
    parts = []
    # get all the path prefixes
    for name in zip.namelist():
        # only check files (not directories)
        if not name.endswith('/'):
            # keep list of path elements (minus filename)
            parts.append(name.split('/')[:-1])
    # now find the common path prefix (if any)
    prefix = os.path.commonprefix(parts)
    if prefix:
        # re-join the path elements
        prefix = '/'.join(prefix) + '/'
    # get the length of the common prefix
    offset = len(prefix)
    # now re-set the filenames
    for zipinfo in zip.infolist():
        name = zipinfo.filename
        # only check files (not directories)
        if len(name) > offset:
            # remove the common prefix
            zipinfo.filename = name[offset:]
            yield zipinfo


def lambda_handler(event, context):

    logger.info('Event %s', event)
    OAUTH_token = event['context']['git-token']
    OutputBucket = event['context']['output-bucket']
    
    headers = {}
    branch = 'master'

    #https://gitlab.com/jaymcconnell/gitlab-test-30/repository/archive.zip?ref=master
    archive_root = event['body-json']['project']['http_url'].strip('.git')
    project_id = event['body-json']['project_id']
    branch = event['body-json']['ref'].replace('refs/heads/', '')
    checkout_sha = event['body-json']['checkout_sha']
    archive_url = "https://gitlab.com/api/v4/projects/{}/repository/archive.zip".format(project_id)
    params = {'private_token': OAUTH_token, 'sha': branch}
    owner = event['body-json']['project']['namespace']
    name = event['body-json']['project']['name']

    s3_archive_file = "%s/%s/%s/%s.zip" % (owner, name, branch, name)
    # download the code archive via archive url
    logger.info('Downloading archive from %s' % archive_url)
    r = requests.get(archive_url, verify=verify, headers=headers, params=params)
    f = StringIO(r.content)
    zip = ZipFile(f)
    path = '/tmp/code'
    zipped_code = '/tmp/zipped_code'
    try:
        shutil.rmtree(path)
        os.remove(zipped_code + '.zip')
    except:
        pass
    finally:
        os.makedirs(path)
    # Write to /tmp dir without any common preffixes
    zip.extractall(path, get_members(zip))

    # add checkout_sha
    checkout_sha_file = open('/tmp/code/checkout_sha.txt', 'w') 
    checkout_sha_file.write(checkout_sha) 
    checkout_sha_file.close()
    
    # Create zip from /tmp dir without any common preffixes
    shutil.make_archive(zipped_code, 'zip', path)
    logger.info("Uploading zip to S3://%s/%s" % (OutputBucket, s3_archive_file))
    s3_client.upload_file(zipped_code + '.zip', OutputBucket, s3_archive_file)
    logger.info('Upload Complete')
