#!/usr/bin/env python
# v 0.0.1
# Ryan Nguyen

# wrapper for RS API challenge

import os
import sys

try:
	os.system('./code/cf_upload.py %s' % sys.argv[1])
except:
	os.system('./code/cf_upload.py')
