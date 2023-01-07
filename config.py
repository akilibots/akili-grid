import os
import pyjson5 as json

def config():
    # Load configuration

    conf = os.getenv('strategy')
    if conf is None:
        with open('data/strategy.json') as f:
            conf = f.read()
    return(json.loads(conf))
    
