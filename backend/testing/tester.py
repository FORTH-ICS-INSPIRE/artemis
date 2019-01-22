from kombu import Connection, Queue, Exchange
from kombu.utils.compat import nested
import os
import time
import json
import sys
import psycopg2


class Tester():

    def __init__(self):
        self.curr_idx = 0
        self.send_cnt = 0
        self.expected_messages = 0

    def getConn(self):
        db_conn = None
        time_sleep_connection_retry = 5
        while db_conn is None:
            time.sleep(time_sleep_connection_retry)
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
                time.sleep(1)
        return db_conn

    def test(self):
        RABBITMQ_HOST = os.getenv('RABBITMQ_HOST')

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

        update_queue = Queue(
            'detection-testing',
            exchange=pg_amq_bridge,
            routing_key='update-insert',
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

        messages = {}
        with open('messages.json', 'r') as f:
            messages = json.load(f)

        send_len = len(messages)

        def validate_message(body, message):
            print('\t- Receiving Batch #{} - Type {} - Remaining {}'.format(self.curr_idx, message.delivery_info['routing_key'], self.expected_messages-1))
            if isinstance(body, dict):
                event = body
            else:
                event = json.loads(body)
            # logging.debug(event)

            if message.delivery_info['routing_key'] == 'update-insert':
                expected = messages[self.curr_idx]['detection_update_response']
            elif message.delivery_info['routing_key'] == 'update':
                expected = messages[self.curr_idx]['detection_hijack_response']
            elif message.delivery_info['routing_key'] == 'hijack-update':
                expected = messages[self.curr_idx]['database_hijack_response']

            for key in set(event.keys()).intersection(expected.keys()):
                if event[key] != expected[key]:
                    sys.exit('Unexpected value for key \"{}\"\nReceived: {}, Expected: {}'
                             .format(key, event[key], expected[key]))

            self.expected_messages -= 1
            if self.expected_messages <= 0:
                self.curr_idx += 1
            message.ack()

        def send_next_message(conn):
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

        def waitExchange(exchange, channel):
            while True:
                try:
                    exchange.declare(passive=True, channel=channel)
                    break
                except Exception:
                    time.sleep(1)

        with Connection(RABBITMQ_HOST) as connection:
            pg_amq_bridge.declare(channel=connection.default_channel)
            print('Waiting for hijack exchange..')
            waitExchange(hijack_exchange, connection.default_channel)
            print('Waiting for update exchange..')
            waitExchange(update_exchange, connection.default_channel)

            db_con = self.getConn()
            db_cur = db_con.cursor()
            query = 'SELECT COUNT(*) FROM process_states WHERE running=True'
            res = (0,)
            while res[0] < 6:
                db_cur.execute(query)
                res = db_cur.fetchall()[0]
                time.sleep(1)
            db_cur.close()
            db_con.close()

            send_cnt = 0
            while send_cnt < send_len:
                self.curr_idx = send_cnt
                send_next_message(connection)
                send_cnt += 1
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
                    while self.curr_idx != send_cnt:
                        time.sleep(0.1)
                        connection.drain_events()
            connection.close()


if __name__ == "__main__":
    obj = Tester()
    obj.test()
