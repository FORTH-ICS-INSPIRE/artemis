from kombu import Connection, Queue, Exchange
from kombu.utils.compat import nested
import os
import time
import json
import psycopg2
import socket
import redis
import hashlib
import pickle
from xmlrpc.client import ServerProxy


class Tester():

    def __init__(self):
        self.initRedis()
        self.initSupervisor()

    def getDbConnection(self):
        '''
        Return a connection for the postgres database.
        '''
        db_conn = None
        time_sleep_connection_retry = 5
        while not db_conn:
            try:
                _db_name = os.getenv('DATABASE_NAME', 'artemis_db')
                _user = os.getenv('DATABASE_USER', 'artemis_user')
                _host = os.getenv('DATABASE_HOST', 'postgres')
                _password = os.getenv('DATABASE_PASSWORD', 'Art3m1s')

                db_conn = psycopg2.connect(
                    dbname=_db_name,
                    user=_user,
                    host=_host,
                    password=_password
                )
            except BaseException:
                time.sleep(time_sleep_connection_retry)
        return db_conn

    def initRedis(self):
        redis_ = redis.Redis(
            host=os.getenv('BACKEND_HOST', 'backend'),
            port=6379
        )
        self.redis = redis_

    def initSupervisor(self):
        SUPERVISOR_HOST = os.getenv('SUPERVISOR_HOST', 'backend')
        SUPERVISOR_PORT = os.getenv('SUPERVISOR_PORT', 9001)
        self.supervisor = ServerProxy(
            'http://{}:{}/RPC2'.format(SUPERVISOR_HOST, SUPERVISOR_PORT))

    def clear(self):
        db_con = self.getDbConnection()
        db_cur = db_con.cursor()
        query = 'delete from bgp_updates; delete from hijacks;'
        db_cur.execute(query)
        db_con.commit()
        db_cur.close()
        db_con.close()

        self.redis.flushall()

        self.curr_idx = 0
        self.send_cnt = 0
        self.expected_messages = 0


    def test(self):
        '''
        Loads a test file that includes crafted bgp updates as input and expected messages as output.
        '''

        RABBITMQ_HOST = os.getenv('RABBITMQ_HOST')

        # exchanges
        update_exchange = Exchange(
            'bgp-update',
            type='direct',
            durable=False,
            delivery_mode=1)

        hijack_exchange = Exchange(
            'hijack-update',
            type='direct',
            durable=False,
            delivery_mode=1)

        pg_amq_bridge = Exchange(
            'amq.direct',
            type='direct',
            durable=True,
            delivery_mode=1)

        # queues
        update_queue = Queue(
            'detection-testing',
            exchange=pg_amq_bridge,
            routing_key='update-update',
            durable=False,
            auto_delete=True,
            max_priority=1,
            consumer_arguments={'x-priority': 1})

        hijack_queue = Queue(
            'hijack-testing',
            exchange=hijack_exchange,
            routing_key='update',
            durable=False,
            auto_delete=True,
            max_priority=1,
            consumer_arguments={'x-priority': 1})

        hijack_db_queue = Queue(
            'hijack-db-testing',
            exchange=pg_amq_bridge,
            routing_key='hijack-update',
            durable=False,
            auto_delete=True,
            max_priority=1,
            consumer_arguments={'x-priority': 1})

        def waitExchange(exchange, channel):
            '''
            Wait passively until the exchange is declared.
            '''
            while True:
                try:
                    exchange.declare(passive=True, channel=channel)
                    break
                except Exception:
                    time.sleep(1)

        with Connection(RABBITMQ_HOST) as connection:
            print('Waiting for pg_amq exchange..')
            waitExchange(pg_amq_bridge, connection.default_channel)
            print('Waiting for hijack exchange..')
            waitExchange(hijack_exchange, connection.default_channel)
            print('Waiting for update exchange..')
            waitExchange(update_exchange, connection.default_channel)

            # query database for the states of the processes
            db_con = self.getDbConnection()
            db_cur = db_con.cursor()
            query = 'SELECT COUNT(*) FROM process_states WHERE running=True'
            res = (0,)
            # wait until all 6 modules are running
            while res[0] < 6:
                print('executing query')
                db_cur.execute(query)
                res = db_cur.fetchall()[0]
                db_con.commit()
                time.sleep(1)
            db_cur.close()
            db_con.close()

            for testfile in os.listdir('testfiles/'):
                self.clear()

                self.curr_test = testfile
                messages = {}
                # load test
                with open('testfiles/{}'.format(testfile), 'r') as f:
                    messages = json.load(f)

                send_len = len(messages)

                def redis_key(prefix, hijack_as, _type):
                    assert isinstance(prefix, str)
                    assert isinstance(hijack_as, int)
                    assert isinstance(_type, str)
                    return hashlib.shake_128(pickle.dumps(
                        [prefix, hijack_as, _type])).hexdigest(16)

                def validate_message(body, message):
                    '''
                    Callback method for message validation from the queues.
                    '''
                    print('\t- Test \"{}\" - Receiving Batch #{} - Type {} - Remaining {}'.format(self.curr_test, self.curr_idx,
                                                                                    message.delivery_info['routing_key'], self.expected_messages - 1))
                    if isinstance(body, dict):
                        event = body
                    else:
                        event = json.loads(body)
                    # logging.debug(event)

                    # distinguish between type of messages
                    if message.delivery_info['routing_key'] == 'update-update':
                        expected = messages[self.curr_idx]['detection_update_response']
                        assert self.redis.exists(
                            event['key']), 'Monitor key not found in Redis'
                    elif message.delivery_info['routing_key'] == 'update':
                        expected = messages[self.curr_idx]['detection_hijack_response']
                        redis_hijack_key = redis_key(
                            event['prefix'],
                            event['hijack_as'],
                            event['type'])
                        assert self.redis.exists(
                            redis_hijack_key), 'Hijack key not found in Redis'
                    elif message.delivery_info['routing_key'] == 'hijack-update':
                        expected = messages[self.curr_idx]['database_hijack_response']
                        if event['active']:
                            assert self.redis.sismember(
                                'persistent-keys', event['key']), 'Persistent key not found in Redis'
                        else:
                            assert not self.redis.sismember(
                                'persistent-keys', event['key']), 'Persistent key found in Redis but should have been removed.'

                    # compare expected message with received one. exit on mismatch.
                    for key in set(event.keys()).intersection(expected.keys()):
                        assert (event[key] == expected[key] or (isinstance(
                                event[key], (list, set)) and set(event[key]) == set(expected[key]))), (
                            'Test \"{}\" - Unexpected value for key \"{}\". Received: {}, Expected: {}'.format(self.curr_test, key, event[key], expected[key]))

                    self.expected_messages -= 1
                    if self.expected_messages <= 0:
                        self.curr_idx += 1
                    message.ack()

                def send_next_message(conn):
                    '''
                    Publish next custom BGP update on the bgp-updates exchange.
                    '''
                    with conn.Producer() as producer:
                        self.expected_messages = len(messages[self.curr_idx]) - 1
                        print('Publishing #{}'.format(self.curr_idx))
                        # logging.debug(messages[curr_idx]['send'])

                        producer.publish(
                            messages[self.curr_idx]['send'],
                            exchange=update_exchange,
                            routing_key='update',
                            serializer='json'
                        )

                with nested(
                        connection.Consumer(
                            hijack_queue,
                            callbacks=[validate_message],
                            accept=['pickle']
                        ),
                        connection.Consumer(
                            update_queue,
                            callbacks=[validate_message],
                        ),
                        connection.Consumer(
                            hijack_db_queue,
                            callbacks=[validate_message]
                        )

                ):
                    send_cnt = 0
                    # send and validate all messages in the messages.json file
                    while send_cnt < send_len:
                        self.curr_idx = send_cnt
                        send_next_message(connection)
                        send_cnt += 1
                        # sleep until we receive all expected messages
                        while self.curr_idx != send_cnt:
                            time.sleep(0.1)
                            try:
                                connection.drain_events(timeout=100)
                            except socket.timeout:
                                # avoid infinite loop by timeout
                                assert False, 'Consumer timeout'

            connection.close()

        def waitProcess(mod, target):
            state = self.supervisor.supervisor.getProcessInfo(mod)['state']
            while state != target:
                time.sleep(0.5)
                state = self.supervisor.supervisor.getProcessInfo(mod)['state']

        self.supervisor.supervisor.stopAllProcesses()

        waitProcess('listener', 0)  # 0 STOPPED
        waitProcess('clock', 0)  # 0 STOPPED
        waitProcess('detection', 0)  # 0 STOPPED
        waitProcess('mitigation', 0)  # 0 STOPPED
        waitProcess('configuration', 0)  # 0 STOPPED
        waitProcess('database', 0)  # 0 STOPPED
        waitProcess('observer', 0)  # 0 STOPPED
        waitProcess('monitor', 0)  # 0 STOPPED

        self.supervisor.supervisor.startProcess('coveralls')

        waitProcess('coveralls', 20)  # 20 RUNNING


if __name__ == "__main__":
    obj = Tester()
    obj.test()
