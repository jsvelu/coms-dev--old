old='\"{}'
new='\"../password'
sed -i "s|${old}|${new}|g" /home/ubuntu/app/env1/lib/python3.8/site-packages/django/contrib/auth/forms.py