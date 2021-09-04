#!/bin/bash
set -e

echo "starting application"
APP_PATH=/home/ubuntu/app
#ENV_FILE=$APP_PATH/.env

cd $APP_PATH

cp -R /home/ubuntu/env1 /home/ubuntu/app
sleep 5

old='\"{}'
new='\"../password'
sed -i "s|${old}|${new}|g" /home/ubuntu/app/env1/lib/python3.8/site-packages/django/contrib/auth/forms.py

#sudo scripts/django.sh

#echo "SET ENVIRONMENT VARIABLES"
#INSTANCE_ID="`wget -qO- http://169.254.169.254/latest/meta-data/instance-id`"
#REGION="`wget -qO- http://169.254.169.254/latest/meta-data/placement/availability-zone | sed -e 's:\([0-9][0-9]*\)[a-z]*\$:\\1:'`"
#ENVIRONMENT="`aws ec2 describe-tags --filters "Name=resource-id,Values=$INSTANCE_ID" "Name=key,Values=environment" --region $REGION --output=text | cut -f5`"
#APPNAME="`aws ec2 describe-tags --filters "Name=resource-id,Values=$INSTANCE_ID" "Name=key,Values=application" --region $REGION --output=text | cut -f5`"
#aws --region $REGION ssm get-parameter --name /$ENVIRONMENT/$APPNAME --output text  --query Parameter.Value > $ENV_FILE

#export $(grep -v '^#' ENV_FILE | xargs)

chmod +x /home/ubuntu/app/nac/manage.py

source env1/bin/activate
#./nac/manage.py showmigrations >> $APP_PATH/migrations.log
#./nac/manage.py migrate --noinput
./nac/manage.py collectstatic --noinput

chmod +x $APP_PATH/configs/gunicorn_start.sh

echo "starting services"
systemctl daemon-reload
systemctl start gunicorn.service
systemctl enable gunicorn.service
systemctl restart nginx.service 
echo "finish application_start.sh"