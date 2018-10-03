import time
from watchdog.observers import Observer as WatchObserver
from watchdog.events import FileSystemEventHandler
from utils.service import Service
from utils import RABBITMQ_HOST
from kombu import Connection, Queue, uuid, Consumer, Producer
import difflib
import logging


log = logging.getLogger('artemis_logger')


class Observer(Service):

    def run_worker(self):
        observer = WatchObserver()

        dirname = './configs'
        filename = 'config.yaml'

        try:
            with Connection(RABBITMQ_HOST) as connection:
                event_handler = self.Handler(dirname, filename, connection)
                observer.schedule(event_handler, dirname, recursive=False)
                observer.start()
                log.info('started')
                self.should_stop = False
                while not self.should_stop:
                    time.sleep(5)
        except BaseException:
            log.exception('exception')
        finally:
            observer.stop()
            observer.join()
            log.info('stopped')

    def exit(self, signum, frame):
        self.should_stop = True

    class Handler(FileSystemEventHandler):

        def __init__(self, d, f, connection):
            super().__init__()
            self.connection = connection
            self.path = '{}/{}'.format(d, f)
            with open(self.path, 'r') as f:
                self.content = f.readlines()

        def on_response(self, message):
            if message.properties['correlation_id'] == self.correlation_id:
                self.response = message.payload

        def on_modified(self, event):
            if event.is_directory:
                return None
            elif event.src_path == self.path:
                with open(self.path, 'r') as f:
                    content = f.readlines()
                # Taken any action here when a file is modified.
                changes = ''.join(difflib.unified_diff(self.content, content))
                if len(changes) > 0:
                    self.response = None
                    self.correlation_id = uuid()
                    callback_queue = Queue(
                        uuid(), exclusive=True, auto_delete=True)
                    with Producer(self.connection) as producer:
                        producer.publish(
                            content,
                            exchange='',
                            routing_key='config-modify-queue',
                            serializer='yaml',
                            retry=True,
                            declare=[callback_queue],
                            reply_to=callback_queue.name,
                            correlation_id=self.correlation_id
                        )
                    with Consumer(self.connection,
                                  on_message=self.on_response,
                                  queues=[callback_queue],
                                  no_ack=True):
                        while self.response is None:
                            self.connection.drain_events()

                    if self.response['status'] == 'accepted':
                        text = 'new configuration accepted:\n{}'.format(
                            changes)
                        log.info(text)
                        self.content = content
                        # with open('./snapshots/config-snapshot-{}.yaml'.format(int(time.time())), 'w') as f:
                        #     f.write(''.join(self.content))
                    else:
                        log.error('invalid configuration:\n{}'.format(content))
                    self.response = None
