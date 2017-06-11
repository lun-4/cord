import logging

import sys
sys.path.append('..')

import cord

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

client = cord.Client(token=None, email='luna@localhost', password='fuck',
                            api_root='http://0.0.0.0:8000/api')

client.run(gw_version=6)
