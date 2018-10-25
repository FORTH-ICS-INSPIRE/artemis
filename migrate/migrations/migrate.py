import os
import json
import psycopg2
import time
import codecs
from codecs import open


def get_target_version():
    target_version = os.getenv('DB_VERSION', None)
    return target_version


def load_migrations_json():
    with open('history.json') as json_data:
        data = json.load(json_data)
    return data


def read_migration_sql_file(filename):
    try:
        with open("migrations/" + filename, mode='r', encoding='utf-8-sig') as f:
            migration_file = f.read()
    except Exception:
        print("Couldn't open migrations/{}".format(filename))
        exit(-1)
    return migration_file


def create_connect_db():
    _db_conn = None
    time_sleep_connection_retry = 5
    while _db_conn is None:
        time.sleep(time_sleep_connection_retry)
        try:
            _db_name = os.getenv('DATABASE_NAME', 'artemis_db')
            _user = os.getenv('DATABASE_USER', 'artemis_user')
            _host = os.getenv('DATABASE_HOST', 'postgres')
            _password = os.getenv('DATABASE_PASSWORD', 'Art3m1s')

            _db_conn = psycopg2.connect(
                dbname=_db_name,
                user=_user,
                host=_host,
                password=_password
            )
        except Exception:
            print("Exception couldn't connect to db.")
    print('PostgreSQL DB created/connected..')
    return _db_conn



def migrate(next_db_version, db_cur):
    print("Executing migration {}..".format(next_db_version['db_version']))
    print("{0}".format(next_db_version['description']))
    migration_command = read_migration_sql_file(next_db_version['file'])
    print("{0}".format(migration_command))
    try:
        db_cur.execute(migration_command)
        db_cur.commit()
    except Exception:
        print("Failed to execute command.")
        exit(-1)
    return True


def update_version(current_db_version, db_cur):
    cmd = "UPDATE db_details SET version={0} WHERE ID={1};".format(current_db_version, 0)
    try:
        db_cur.execute(cmd)
        db_cur.commit()
    except Exception:
        print("Failed to execute command.")
        exit(-1)


def start_migrations(current_db_version, target_db_version, db_conn):
    db_cur = db_conn.cursor()
    migration_data = load_migrations_json()
    if current_db_version == None:
        current_db_version = 0

    while(current_db_version != target_db_version):
        next_db_version = int(current_db_version) + 1
        if next_db_version in migration_data:
            status = migrate(migration_data[str(next_db_version)], db_cur)
            if status:
                update_version(current_db_version, db_cur)
        else:
            print("Missing version to migrate..")
            exit(-1)
        current_db_version = str(next_db_version)
    db_cursor.close()


def extract_db_version(db_conn):
    try:
        cur = db_conn.cursor()
        cur.execute('SELECT version from db_details')     
        version = cur.fetchone()
    except psycopg2.DatabaseError:
        return None
    return version


if __name__ == "__main__":
    db_conn = create_connect_db()
    target_db_version = get_target_version()
    current_db_version = extract_db_version()

    if target_db_version == None:
        print("Couldn't identify the version of the code.")
        exit(-1)

    if target_db_version != current_db_version:
        msg = "The db schema is old.\n"
        msg += "Migrating from version {0} to {1}".format(current_db_version, target_db_version)
        print(msg)
        result = start_migrations(current_db_version, target_db_version, db_conn)
        print("The db schema has been succesfully updated!")
    else:
        print("The db schema is uptodate.")

    db_conn.close()
