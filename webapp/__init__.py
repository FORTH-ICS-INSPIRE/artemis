import os

__all__ = ['webapp']


this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
db_dir = '{}/db'.format(upper_dir)
if not os.path.isdir(db_dir):
    os.mkdir(db_dir)
