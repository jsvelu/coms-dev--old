#!/bin/bash
APP_DIR=/home/ubuntu/app
ENV_FILE=$APP_DIR/.env
LOGFILE=$APP_DIR/logs/gunicorn.log
ADDRESS=0.0.0.0:8000
NUM_WORKERS=3

echo "Starting application as `whoami`"

# Activate the virtual environment
source $APP_DIR/env1/bin/activate

# export variables defined in paramstore
export $(grep -v '^#' $ENV_FILE | xargs)

cd $APP_DIR/nac

# Start your Django Unicorn
$APP_DIR/env1/bin/gunicorn wsgi \
    --workers $NUM_WORKERS \
    --bind=$ADDRESS \
    --log-level=debug \
    --log-file=$LOGFILE \
    --timeout 120

