#!/bin/sh
exec sudo -n /usr/bin/python3 /usr/local/lib/hr-frontend-receive.py "$SSH_ORIGINAL_COMMAND"
