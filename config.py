import os
import json

def config():
    # Load configuration

    conf = os.getenv('strategy')
    if conf is None:
        with open('strategy.json') as f:
            conf = f.read()
    return(json.loads(conf))