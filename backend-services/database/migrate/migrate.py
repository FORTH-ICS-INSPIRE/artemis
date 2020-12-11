import os
import subprocess
import time
from codecs import open as c_open

import psycopg2
import ujson as json


def get_target_version():
    print("Getting target version...")
    target_version = os.getenv("DB_VERSION", None)
    print("-> Target version is: {}".format(target_version))
    return target_version


def load_migrations_json():
    print("Loading migrations file...")
    with c_open("/root/migrate/migrations/target_steps.json") as json_data:
        data = json.load(json_data)
    return data


def read_migration_sql_file(filename):
    print("Reading migration .sql file: {}...".format(filename))
    try:
        with c_open(
            "/root/migrate/migrations/scripts/" + filename,
            mode="r",
            encoding="utf-8-sig",
        ) as f:
            migration_file = f.read()
    except Exception:
        print("Couldn't open migrations script: {}".format(filename))
        exit(-1)
    return migration_file


def create_connect_db():
    print("Connecting to db...")
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
                application_name="backend-migrate",
                dbname=_db_name,
                user=_user,
                host=_host,
                port=_port,
                password=_password,
            )
        except Exception:
            print("Exception couldn't connect to db.\nRetrying in 5 seconds...")
    print("PostgreSQL DB created/connected..")
    return _db_conn


def migrate_sql_file(filename, db_cur, db_conn):
    migration_command = read_migration_sql_file(filename)
    print(" - - - - - \n\n {0} \n\n - - - - - ".format(migration_command))
    try:
        db_cur.execute(migration_command)
        db_conn.commit()
    except psycopg2.DatabaseError as e:
        db_conn.rollback()
        print("Failed to execute command. \n {}".format(e))
        exit(-1)


def migrate_python_file(filename):
    file_ = "/root/migrate/migrations/scripts/" + filename
    result = ""
    try:
        print("Executing -> {}".format(file_))
        result = subprocess.check_output(["/usr/local/bin/python", file_], shell=False)
    except Exception:
        print("subprocess failed: {}".format(result))
        exit(-1)

    if "success" not in result.decode("utf-8"):
        print(
            "The execution of python migration file '{0}' returned the following error:\n {1}".format(
                file_, result
            )
        )
        exit(-1)


def migrate_bash_file(filename):
    file_ = "/root/migrate/migrations/scripts/" + filename
    result = ""
    try:
        print("Executing -> {}".format(file_))
        subprocess.run(["/bin/chmod", "+x", file_], shell=False)
        result = subprocess.check_output(["/bin/bash", file_], shell=False)
    except Exception:
        print("subprocess failed: {}".format(result))
        exit(-1)

    if "success" not in result.decode("utf-8"):
        print(
            "The execution of bash migration file '{0}' returned the following error:\n {1}".format(
                file_, result
            )
        )
        exit(-1)


def migrate(next_db_version, db_cur, db_conn):
    print("Executing migration {}...".format(next_db_version["db_version"]))
    print("{0}".format(next_db_version["description"]))

    if not isinstance(next_db_version["file"], list):
        next_db_version["file"] = [next_db_version["file"]]
    for filename in next_db_version["file"]:
        if ".sql" in filename:
            migrate_sql_file(filename, db_cur, db_conn)
        elif ".py" in filename:
            migrate_python_file(filename)
        elif ".sh" in filename:
            migrate_bash_file(filename)
        else:
            print("The file type of '{}' is currently not supported".format(filename))
            exit(-1)
    return True


def update_version(current_db_version, db_cur, db_conn):
    print("Updating db version to {}...".format(current_db_version))
    cmd = "UPDATE db_details SET version=%s, upgraded_on=now();"
    try:
        db_cur.execute(cmd, (current_db_version,))
        db_conn.commit()
    except Exception:
        db_conn.rollback()
        print("Failed to execute command.")
        exit(-1)


def start_migrations(current_db_version, target_db_version, db_conn):
    print("Starting migrations...")

    db_cur = db_conn.cursor()
    migration_data = load_migrations_json()

    count_migration = 0
    total_migrations = int(target_db_version) - int(current_db_version)

    while current_db_version < target_db_version:
        next_db_version = int(current_db_version) + 1
        next_db_version_key_str = str(next_db_version)
        if next_db_version_key_str in migration_data["migrations"]:
            status = migrate(
                migration_data["migrations"][next_db_version_key_str], db_cur, db_conn
            )
            if status:
                current_db_version = int(current_db_version) + 1
                update_version(current_db_version, db_cur, db_conn)
            count_migration += 1
        else:
            print("Missing version to migrate...")
            exit(-1)
        current_db_version = next_db_version
        print("Migration {0}/{1}".format(count_migration, total_migrations))
    db_cur.close()


def extract_db_version(db_conn):
    print("Getting db version...")
    try:
        cur = db_conn.cursor()
        cur.execute("SELECT version from db_details")
        version = cur.fetchone()[0]
    except psycopg2.DatabaseError:
        db_conn.rollback()
        print("db version not found")
        version = None

    if version is None:
        version = 0
    print("-> Current db version is: {}".format(version))
    return version


if __name__ == "__main__":

    print("Initializing migration...")
    db_conn = create_connect_db()
    target_db_version = int(get_target_version())
    current_db_version = int(extract_db_version(db_conn))

    if target_db_version is None:
        print("Couldn't identify the version of the code.")
        exit(-1)

    if current_db_version < target_db_version:
        msg = "The db schema is old.\n"
        msg += "Migrating from version {0} to {1}".format(
            current_db_version, target_db_version
        )
        print(msg)
        result = start_migrations(current_db_version, target_db_version, db_conn)
        print("The db schema has been succesfully updated!")
    else:
        print("The db schema is uptodate.")

    db_conn.close()
