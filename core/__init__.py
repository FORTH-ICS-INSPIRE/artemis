__all__ = ['core']

import traceback

class ArtemisError(Exception):
    def __init__(self, _type, _where):
        self.type = _type
        self.where = _where

        message = 'type: {}, at: {}'.format(_type, _where)

        # Call the base class constructor with the parameters it needs
        super().__init__(message)

def exception_handler(f):
    def wrapper(*args):
        try:
            return f(*args)
        except Exception as e:
            traceback.print_exc()
            return False
    return wrapper
