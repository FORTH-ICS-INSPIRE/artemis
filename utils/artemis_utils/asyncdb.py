#!/usr/bin/env python
import asyncpg

from artemis_utils import get_logger

LIMIT_RETRIES = 5

# logger
# import logging
# logging.basicConfig(level=logging.DEBUG)
log = get_logger()


class DB:
    def __init__(
            self,
            application_name,
            user,
            password,
            host,
            port,
            database,
            reconnect=True,
            autocommit=False,
            readonly=False,
    ):
        self.application_name = application_name
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.database = database
        self._pool = None
        self._connection = None
        self._cursor = None
        self.reconnect = reconnect
        self.autocommit = autocommit
        self.readonly = readonly

    async def init(self):
        if not self._pool:
            self._pool = await asyncpg.create_pool(
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port,
                database=self.database,
                timeout=3,
            )
        log.debug("connection init")
        await self.connect()

    async def connect(self):
        if not self._connection:
            self._connection = await self._pool.acquire()
            log.debug("connection established")

    async def execute(self, query, vals=None):
        log.debug("execute query {}".format(query))
        if vals:
            return await self._connection.fetch(query, *vals)
        else:
            return await self._connection.fetch(query)

    async def execute_batch(self, query, vals):
        if not vals:
            return None
        log.debug("execute_batch query {}, len vals {}".format(query, len(vals)))
        await self._connection.executemany(query, vals)

    async def execute_values(self, query, vals):
        if not vals:
            return None
        log.debug("execute_values query {}, len vals {}".format(query, len(vals)))
        await self._connection.executemany(query, vals)
