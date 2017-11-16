import peewee as pw
from peewee import *
import time
"""
class pformatBGP(Model):
    service = CharField()
    collector = CharField()
    type_of_bgp = CharField()
    #prefix = InetAddressField()
    as_path = ArrayField(PositiveIntegerField)
    next_hop = InetAddressField()
    timestamp = DateTimeField()
    #peer = InetAddressField()
    peer_asn = PositiveIntegerField()
    time_added = DateTimeField()

    class Meta:
        database = db
"""
class DB():

	db_host = "localhost"
	db_user = "artemis_user"
	db_password = "artemisUser"
	db_name = "artemis_prototype"
	db_conn = None

	def __init__(self):
		self.connect()
	

	def create_tables(self):
		try:
			self.db_conn.create_tables([pformatBGP])
		except:
			print("Error while creating tables to the database.")


	def connect(self):
		try:
			db_conn = pw.MySQLDatabase(self.db_name,
								host = self.db_host,
								user = db_user,
								passwd = db_password,
								db = self.db_name,
								port=3306)
		except:
			print("Database failed to connect.")
			exit(-1)

	def insert_entry(self, pformat_obj):
		
		try:
			pformatBGP.create( service = pformat_obj['service'],
								collector = pformat_obj['collector'],
								type_of_bgp = pformat_obj['type'],
								prefix = pformat_obj['prefix'],
								as_path = pformat_obj['as_path'],
								next_hop = pformat_obj['next_hop'],
								timestamp = pformat_obj['timestamp'],
								peer = pformat_obj['peer'],
								peer_asn = pformat_obj['peer_asn'],
								time_added = time.time()
								)
		except:
			print("Error while writing entry to the database.")















