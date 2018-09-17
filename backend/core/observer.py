import time
import os
import sys
from watchdog.observers import Observer as WatchObserver
from watchdog.events import FileSystemEventHandler
import traceback
from utils.service import Service
from utils import log
import difflib


class Observer(Service):


    def run_worker(self):
        self.observer = WatchObserver()

        dirname = './configs'
        filename = 'config.yaml'
        event_handler = self.Handler(dirname, filename)

        self.observer.schedule(event_handler, dirname, recursive=False)
        self.observer.start()
        log.info('Observer Started..')
        self.should_stop = False
        while not self.should_stop:
            time.sleep(5)
        self.observer.stop()
        self.observer.join()
        log.info('Observer Stopped..')


    def exit(self, signum, frame):
        self.should_stop = True


    class Handler(FileSystemEventHandler):


        def __init__(self, d, f):
            super().__init__()
            self.path = '{}/{}'.format(d, f)
            with open(self.path, 'r') as f:
                self.content = f.readlines()


        def on_modified(self, event):
            if event.is_directory:
                return None
            elif event.src_path == self.path:
                with open(self.path, 'r') as f:
                    content = f.readlines()
                # Taken any action here when a file is modified.
                changes = ''.join(difflib.unified_diff(self.content, content))
                if len(changes) > 0:
                    text = 'CONFIGURATION FILE MODIFICATION\n{}'.format(changes)
                    log.info(text)
                    self.content = content
                    with open('./snapshots/config-snapshot-{}.yaml'.format(int(time.time())), 'w') as f:
                        f.write(''.join(self.content))


