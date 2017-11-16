from core.db import DB

class Pformat():

	###
	# json object 
	# 'service':
	# 'collector' 
	# 'type'
	# 'prefix'
	# 'as_path'
	# 'next_hop'
	# 'timestamp'
	# 'peer'
	# 'peer_asn'
	
	available_parsers = ['RIPEris', 'BGPmon', 'ExaBGP']
	ris_fields = ['type', 'prefix', 'as_path', 'next_hop', 'timestamp', 'peer', 'peer_asn']
	bgpmon_fields = ['timestamp', 'prefix', 'as_path', 'peer', 'type']
	exabgp_fields = []

	def __init__(self, raw_log_queue, parsed_log_queue):
		self.raw_log_queue = raw_log_queue
		self.parsed_log_queue = parsed_log_queue
		self.process_field = {'RIPEris': self.transform_ris_format,
							'BGPmon': self.transform_bgpmon_format,
							'ExaBGP': self.transform_exabgp_format }
		self.parse_queue()


	def parse_queue(self):

		while(True):
			try:

				raw_log = self.raw_log_queue.get()
				print(raw_log)
				if(raw_log[0] in self.available_parsers):
					self.process_field[raw_log[0]](raw_log[1], raw_log[2])

			except:
				print("Error on raw log queue parsing.")



	def transform_ris_format(self, monitor, bgp_msg):
		
		try:
			#Find missing attributes
			missing_attributes = list(set(self.ris_fields) - set(bgp_msg))
			for attr in missing_attributes:
				bgp_msg[attr] = None

			pformat_obj = {'service': 'RIPEris', 
							'collector': monitor, 
							'type': bgp_msg['type'],
							'prefix': bgp_msg['prefix'],
							'as_path': bgp_msg['path'],
							'next_hop': bgp_msg['next_hop'],
							'timestamp': bgp_msg['timestamp'],
							'peer': bgp_msg['peer'],
							'peer_asn': bgp_msg['peer_asn']
							}

			self.parsed_log_queue.put(pformat_obj)
			self.store_to_db(pformat_obj)

		except:
			print("Error on Pformat RIPEris format transformation.")



	def transform_bgpmon_format(self, monitor, bgp_msg):
		try:
			#Find missing attributes
			missing_attributes = list(set(self.bgpmon_fields) - set(bgp_msg))
			for attr in missing_attributes:
				bgp_msg[attr] = None

			pformat_obj = {'service': 'BGPmon', 
							'collector': 'all', 
							'type': bgp_msg['type'],
							'prefix': bgp_msg['prefix'],
							'as_path': bgp_msg['path'],
							'next_hop': None,
							'timestamp': bgp_msg['timestamp'],
							'peer': bgp_msg['peer'],
							'peer_asn': None
							}

			self.parsed_log_queue.put(pformat_obj)
			self.store_to_db(pformat_obj)

		except:
			print("Error on Pformat RIPEris format transformation.")


	def transform_exabgp_format(self, monitor, bgp_msg):
		try:
			#Find missing attributes
			missing_attributes = list(set(self.bgpmon_fields) - set(bgp_msg))
			for attr in missing_attributes:
				bgp_msg[attr] = None

			pformat_obj = {'service': 'BGPmon', 
							'collector': 'all', 
							'type': bgp_msg['type'],
							'prefix': bgp_msg['prefix'],
							'as_path': bgp_msg['path'],
							'next_hop': None,
							'timestamp': bgp_msg['timestamp'],
							'peer': bgp_msg['peer'],
							'peer_asn': None
							}

			self.parsed_log_queue.put(pformat_obj)
			self.store_to_db(pformat_obj)

		except:
			print("Error on Pformat RIPEris format transformation.")

	def store_to_db(self, pformat_obj):
		pass
