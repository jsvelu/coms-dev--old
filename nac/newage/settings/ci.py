"""Development settings and globals."""



import distutils as _distutils
import hashlib as _hashlib
import os as _os
import random as _random
import sys as _sys

from .aws_base import *

########## EMAIL CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/topics/email/#topic-email-backends
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# See: https://docs.djangoproject.com/en/dev/ref/settings/#email-subject-prefix
EMAIL_SUBJECT_PREFIX = '[New Age CI] '

# See: https://docs.djangoproject.com/en/dev/ref/settings/#server-email
SERVER_EMAIL = 'server-error@newagecaravans.com.au'
########## END EMAIL CONFIGURATION

########## HOST CONFIGURATION
# See: https://docs.djangoproject.com/en/1.5/releases/1.5/#allowed-hosts-required-in-production
ALLOWED_HOSTS = [
    '127.0.0.1',
    'localhost',
    get_env_setting('SERVER_HOSTNAME'),
    get_env_setting('SELENIUM__STANDALONE_CHROME_PORT_4444_TCP_ADDR'),
]

INTERNAL_IPS = [
    '127.0.0.1',
    get_env_setting('SERVER_HOSTNAME'),
    get_env_setting('SELENIUM__STANDALONE_CHROME_PORT_4444_TCP_ADDR'),
]

########## END HOST CONFIGURATION

########## DATABASE CONFIGURATION
# We use (almost) the same settings variables as the base config

# Account for mysql version difference (live is running on mysql 5.1)
_options = DATABASES['default']['OPTIONS']
_options['init_command'] =  'SET default_storage_engine=INNODB'

########## END DATABASE CONFIGURATION

########## SECRET CONFIGURATION
# you can replace this with a random static string if you want password reset tokens etc to work across restarts
SECRET_KEY = get_env_setting('SECRET_KEY', _hashlib.sha256(str(_random.SystemRandom().getrandbits(256)).encode('ascii')).hexdigest(),)
########## END SECRET CONFIGURATION

BODY_ENV_CLASS = 'env-ci'

# turn off logging of uninteresting requests
LOGGING['loggers']['werkzeug']['level'] = 'WARNING'

# Turn on sql logging
if _distutils.util.strtobool(get_env_setting('DEBUG_SQL', '0')):
    # Beware of unexpected side-effects of DEBUG; there's no way of turning on DEBUG just for SQL logging
    DEBUG = True
    DEBUG_WEBPACK = False
    print("Enabling SQL dump (pid %d)\n" % _os.getpid(), file=_sys.stderr)
    LOGGING['loggers']['django']['level'] = 'DEBUG'
    LOGGING['loggers']['django']['handlers'].append('console')

#EGM_API_USERNAME = get_env_setting('EGM_API_USERNAME')
#EGM_API_PASSWORD = get_env_setting('EGM_API_PASSWORD')
#EGM_MANUFACTURE_NAME = 'New Age'
#EGM_IDENTIFICATION_TOKEN = get_env_setting('EGM_IDENTIFICATION_TOKEN')
#EGM_DEFAULT_ACTION_TYPE = 'walkin'

print("Loaded CI config (pid %d)\n" % _os.getpid(), file=_sys.stderr)

if get_env_setting('CI_JOB_NAME', '') != 'test-unit':
    # Frontend tests should always run with mocked dates
    assert _distutils.util.strtobool(get_env_setting('MOCK_DATES', '0'))

# Salesforce settings
SALESFORCE_API_BASE_URL = 'https://lead-api-test.qrsolutions.com.au/QrsAGNewAGEAPI'
SALESFORCE_API_AUTH = '5316l54j-d6d9-11e6-80f5-76304decesb7'

DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
