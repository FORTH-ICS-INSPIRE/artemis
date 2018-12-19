import os


def get_app_base_path():
    path_ = os.path.dirname(os.path.realpath(__file__))
    return path_.replace('/utils', '')

