import os
import pyjson5

def config():
    # Load configuration
    conf_string = os.getenv('strategy')
    if conf_string is None:
        with open("data/strategy.json", "rt") as f:
            conf_string = f.read()
    
    return pyjson5.decode(conf_string)
