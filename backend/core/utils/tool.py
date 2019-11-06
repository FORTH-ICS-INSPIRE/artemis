#!/usr/bin/env python
import time

import psycopg2.extras
from utils import get_logger

ISOLEVEL = psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT

LIMIT_RETRIES = 5

log = get_logger()


class DB:
    def __init__(
        self,
        user,
        password,
        host,
        port,
        database,
        reconnect=True,
        autocommit=False,
        readonly=False,
    ):
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.database = database
        self._connection = None
        self._cursor = None
        self.reconnect = reconnect
        self.autocommit = autocommit
        self.readonly = readonly
        self.init()

    def connect(self, retry_counter=0):
        if not self._connection:
            try:
                self._connection = psycopg2.connect(
                    user=self.user,
                    password=self.password,
                    host=self.host,
                    port=self.port,
                    database=self.database,
                    connect_timeout=3,
                )
                retry_counter = 0
                self._connection.set_session(
                    autocommit=self.autocommit, readonly=self.readonly
                )
                return self._connection
            except psycopg2.OperationalError as error:
                if not self.reconnect or retry_counter >= LIMIT_RETRIES:
                    raise error
                retry_counter += 1
                log.error(
                    "got error {}. reconnecting {}".format(
                        str(error).strip(), retry_counter
                    )
                )
                time.sleep(5)
                self.connect(retry_counter)
            except (Exception, psycopg2.Error) as error:
                raise error

    def cursor(self):
        if not self._cursor or self._cursor.closed:
            if not self._connection:
                self.connect()
            self._cursor = self._connection.cursor()
            return self._cursor

    def execute(self, query, vals=None, retry_counter=0, fetch_one=False):
        try:
            if vals:
                self._cursor.execute(query, vals)
            else:
                self._cursor.execute(query)
            retry_counter = 0
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as error:
            if retry_counter >= LIMIT_RETRIES:
                raise error
            retry_counter += 1
            log.error(
                "got error {}. retrying {}".format(str(error).strip(), retry_counter)
            )
            time.sleep(1)
            self.reset()
            self.execute(query, vals, retry_counter)
        except (Exception, psycopg2.Error) as error:
            if not self.readonly:
                self._connection.rollback()
            raise error
        else:
            if not self.readonly:
                self._connection.commit()
        if self.readonly:
            if self.fetch_one:
                return self._cursor.fetchone()
            else:
                return self._cursor.fetchall()

    def execute_batch(self, query, vals, page_size=1000, retry_counter=0):
        try:
            psycopg2.extras.execute_batch(
                self._cursor, query, vals, page_size=page_size
            )
            retry_counter = 0
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as error:
            if retry_counter >= LIMIT_RETRIES:
                raise error
            retry_counter += 1
            log.error(
                "got error {}. retrying {}".format(str(error).strip(), retry_counter)
            )
            time.sleep(1)
            self.reset()
            self.execute_batch(query, vals, page_size, retry_counter)
        except (Exception, psycopg2.Error) as error:
            if not self.readonly:
                self._connection.rollback()
            raise error
        else:
            if not self.readonly:
                self._connection.commit()
        if self.readonly:
            return self._cursor.fetchall()

    def execute_values(self, query, vals, page_size=1000, retry_counter=0):
        try:
            psycopg2.extras.execute_values(
                self._cursor, query, vals, page_size=page_size
            )
            retry_counter = 0
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as error:
            if retry_counter >= LIMIT_RETRIES:
                raise error
            retry_counter += 1
            log.error(
                "got error {}. retrying {}".format(str(error).strip(), retry_counter)
            )
            time.sleep(1)
            self.reset()
            self.execute_values(query, vals, page_size, retry_counter)
        except (Exception, psycopg2.Error) as error:
            if not self.readonly:
                self._connection.rollback()
            raise error
        if not self.readonly:
            self._connection.commit()

    def reset(self):
        self.close()
        self.connect()
        self.cursor()

    def close(self):
        if self._connection:
            if self._cursor:
                self._cursor.close()
            self._connection.close()
            log.info("PostgreSQL connection is closed")
        self._connection = None
        self._cursor = None

    def init(self):
        self.connect()
        self.cursor()
