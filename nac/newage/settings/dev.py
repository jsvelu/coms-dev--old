"""Development settings and globals."""



import distutils as _distutils
import errno as _errno
import hashlib as _hashlib
import random as _random
import re as _re
import subprocess as _subprocess
import sys as _sys

from unipath import Path as _Path

from .base import *

# ######### DEBUG CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = True
DEBUG_WEBPACK = False
CSRF_COOKIE_SECURE = False

for _tpl in TEMPLATES:
    _tpl['OPTIONS']['debug'] = DEBUG

ALLOWED_HOSTS += [
    '127.0.0.1',
    'localhost',
    '52.63.118.181',
    '*',
]

INTERNAL_IPS = [
    '127.0.0.1',
]

# "NO_DEBUG_TOOLBAR=1 ./manage.py runserver" to run server w/ django debug toolbar off.
if not _distutils.util.strtobool(get_env_setting('NO_DEBUG_TOOLBAR', '0')):
    INSTALLED_APPS += (
        'debug_toolbar',
    )
    MIDDLEWARE += (
        'debug_toolbar.middleware.DebugToolbarMiddleware',
    )
    DEBUG_TOOLBAR_CONFIG = {
        'SKIP_TEMPLATE_PREFIXES': (
            'django/forms/widgets/', 'admin/widgets/',
            'floppyforms/', # needed to avoid infinite loops
        ),
    }

# Use default application for runserver
WSGI_APPLICATION = None

STATICFILES_DIRS += (
    ('bower_components', _Path(PROJECT_DIR, 'frontend/bower_components')),
)

BODY_ENV_CLASS = 'env-dev'

# ######### END DEBUG CONFIGURATION


# ######### DATABASE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'newage',
        'OPTIONS': {
           'init_command': 'SET default_storage_engine=INNODB',
            'read_default_file': '~/.my.cnf',
       },
       'ENGINE': 'django.db.backends.mysql',
       'NAME': 'coms_development',
       "HOST": '3.105.47.164',
       "PORT": 3306,
       "USER": 'webuser',
       "PASSWORD": 'DM2Qs8ATtJs8a',
       'OPTIONS': {
           'init_command': 'SET default_storage_engine=INNODB',
           'read_default_file': '~/.my.cnf',
        },
    }
}
# ######### END DATABASE CONFIGURATION

if DEBUG:
    WEBPACK_LOADER['DEFAULT']['BUNDLE_DIR_NAME'] = 'dist/prod/'
    WEBPACK_LOADER['DEFAULT']['STATS_FILE'] = _Path(PROJECT_DIR, 'frontend/dist/prod/webpack-stats.json')

########## SECRET CONFIGURATION
# you can replace this with a random static string if you want password reset tokens etc to work across restarts
# SECRET_KEY = get_env_setting('SECRET_KEY', _hashlib.sha256(str(_random.SystemRandom().getrandbits(256)).encode('ascii')).hexdigest(),)
SECRET_KEY = get_env_setting('SECRET_KEY', '')
if SECRET_KEY == '':
    try:
        with open(_Path(_Path(__file__).parent, 'SECRET_KEY'), 'rb') as _fp:
            _unhashed_secret = _fp.read()
    except IOError as e:
        if e.errno != _errno.ENOENT:
            raise
        with open(_Path(_Path(__file__).parent, 'SECRET_KEY'), 'wb') as _fp:
            _unhashed_secret = '\n'.join([
                '# This is an automatically generated secret key',
                '# DO NOT COMMIT THIS',
                '# DO NOT USE THIS FOR PRODUCTION',
                _hashlib.sha256(str(_random.SystemRandom().getrandbits(256)).encode('ascii')).hexdigest(),
            ])
            _fp.write(_unhashed_secret)
    # This slows down startup by 0.3-0.4 sec, but ensures that we have a semi-randomised output that will fail
    # on linux, so should make it harder to predict the SECRET_KEY if it is accidentally committed to source
    _proc = _subprocess.Popen(['system_profiler', 'SPStorageDataType'], stdout=_subprocess.PIPE)
    _unhashed_secret += '\n' + '\n'.join(sorted(line for line in _proc.communicate()[0].splitlines() if 'UUID' in line))
    SECRET_KEY = _hashlib.sha256(_unhashed_secret.encode('ascii')).hexdigest()
########## END SECRET CONFIGURATION

if DEBUG:
    LOGGING['loggers']['werkzeug']['level'] = 'DEBUG'

# Note that manage.py runserver forks processes so this will unavoidably display multiple times
_dev_notice_printed = False
if not _dev_notice_printed:
    # Only prints dev config if no arguments (makes bash tab-complete cleaner)
    if _re.search(r'(^|/)(manage\.py|django-admin(\.py)?)$', _sys.argv[0]) and len(_sys.argv) != 1:
        import os as _os
        # print("Loaded dev config (pid %d)\n" % _os.getpid(), file=_sys.stderr)
        _dev_notice_printed = True


EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


EGM_API_USERNAME = 'allianceintergration'
EGM_API_PASSWORD = 'BgVAuh2q5He5mnEsxdG6'
EGM_MANUFACTURE_NAME = 'New Age'
EGM_DEFAULT_ACTION_TYPE = 'walkin'

EGM_IDENTIFICATION_TOKEN = 'zTGckmggfnZ2VhWGPqYaLryAdmu8tDkXgpw05g6g0y4cRnCFLv9bj5lrzN56kKCg'

EGM_TEST_DEALERREP_EMAIL = 'alliance@egmserver.com.au'
EGM_TEST_DEALER_CODE = '2016'

# e-GoodManners settings
EGM_API_URL = 'http://datafeed.egmserver.com.au/webservices/newage.asmx?wsdl'


# Salesforce settings
SALESFORCE_API_BASE_URL = 'https://lead-api-test.qrsolutions.com.au/QrsAGNewAGEAPI'
SALESFORCE_API_AUTH = '5316l54j-d6d9-11e6-80f5-76304decesb7'

# AWS S3 access details
DEFAULT_FILE_STORAGE = 'newage.custom_storages.MediaStorage'
AWS_STORAGE_BUCKET_NAME = 'coms-dev'
AWS_ACCESS_KEY_ID = get_env_setting('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = get_env_setting('AWS_SECRET_ACCESS_KEY')
AWS_DEFAULT_ACL = None

MEDIAFILES_LOCATION = 'media'
