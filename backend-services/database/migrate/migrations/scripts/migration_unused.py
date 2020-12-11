import hashlib
import os
import time

import psycopg2.extras
import ujson as json


def create_connect_db():
    _db_conn = None
    time_sleep_connection_retry = 5
    while _db_conn is None:
        time.sleep(time_sleep_connection_retry)
        try:
            _db_name = os.getenv("DB_NAME", "artemis_db")
            _user = os.getenv("DB_USER", "artemis_user")
            _host = os.getenv("DB_HOST", "postgres")
            _port = os.getenv("DB_PORT", 5432)
            _password = os.getenv("DB_PASS", "Art3m1s")

            _db_conn = psycopg2.connect(
                application_name="backend-migration",
                dbname=_db_name,
                user=_user,
                host=_host,
                port=_port,
                password=_password,
            )
        except Exception:
            print("Exception couldn't connect to db.\nRetrying in 5 seconds...")
    return _db_conn


def get_hash(obj):
    return hashlib.shake_128(json.dumps(obj).encode("utf-8")).hexdigest(16)


def calculate_new_keys(cur):
    map_old_new_keys = {}
    query = "SELECT prefix, hijack_as, type, time_detected, key FROM hijacks"
    cur.execute(query)
    entries = cur.fetchall()
    for item_ in entries:
        old_key_ = item_[4]
        new_key_ = calculate_new_key(
            item_[0], item_[1], item_[2], str("{0:.6f}".format(item_[3].timestamp()))
        )
        map_old_new_keys[old_key_] = new_key_
    return map_old_new_keys


def calculate_new_key(prefix, hijacker, hij_type, time_detected):
    return get_hash([prefix, hijacker, hij_type, time_detected])


def update_hijack_keys(cur, map_old_new_keys):
    values_ = []
    for old_key_ in map_old_new_keys:
        new_key_ = map_old_new_keys[old_key_]
        values_.append((new_key_, old_key_))

    query = "UPDATE hijacks SET key=data.new FROM (VALUES %s) AS data (new, old) WHERE key=data.old"

    try:
        psycopg2.extras.execute_values(cur, query, values_, page_size=1000)
    except Exception:
        print("error on hijack key update")
        exit(-1)


def update_bgp_updates(cur, map_old_new_keys):
    values_ = []
    for old_key_ in map_old_new_keys:
        new_key_ = map_old_new_keys[old_key_]
        values_.append((old_key_, new_key_))

    query = "UPDATE bgp_updates SET hijack_key = array_replace(hijack_key, data.old, data.new) FROM (VALUES %s) AS data (old, new) WHERE data.old = ANY(hijack_key)"

    try:
        psycopg2.extras.execute_values(cur, query, values_, page_size=1000)
    except Exception:
        print("error on bgp_updates key update")
        exit(-1)


def main():
    db_conn = create_connect_db()
    cur = db_conn.cursor()
    map_old_new_keys = calculate_new_keys(cur)
    update_hijack_keys(cur, map_old_new_keys)
    update_bgp_updates(cur, map_old_new_keys)
    print("success")


main()
