import radix

class Detection():

	def __init__(self, configs, parsed_log_queue, monitors):

		self.configs_ = configs
		self.parsed_log_queue = parsed_log_queue
		self.monitors = monitors

		self.prefix_tree = radix.Radix()

		self.init_detection()
		self.parse_queue()


	def init_detection(self):

		for config in self.configs_:
			
			for prefix in self.configs_[config]['prefixes']:
				node = self.prefix_tree.add(str(prefix))
				node.data["origin_asns"] = self.configs_[config]['origin_asns']
				node.data["neighbors"] = self.configs_[config]['neighbors']
				node.data["mitigation"] = self.configs_[config]['mitigation']


	def parse_queue(self):

		while(True):
			try:
				parsed_log = self.parsed_log_queue.get()
				if( not self.detect_origin_hijack(parsed_log) ):
					if( not self.detech_type_1_hijack(parsed_log) ):
						pass


			except:
				print("Error on raw log queue parsing.")


	def detect_origin_hijack(self, bgp_msg):

		try:
			if(len(bgp_msg['as_path']) > 0):
				origin_asn = int(bgp_msg['as_path'][-1])
				prefix_node = self.prefix_tree.search_best(bgp_msg['prefix'])
				if(prefix_node is not None):
					if(origin_asn not in prefix_node.data['origin_asns']):
						## Trigger hijack


						print("HIJACK TYPE 0 detected!")
						return True
			return False
		except:
			print("Error on detect origin hijack.")


	def detech_type_1_hijack(self, bgp_msg):


		try:
			if(len(bgp_msg['as_path']) > 1):
				first_neighbor_asn = int(bgp_msg['as_path'][-2])
				prefix_node = self.prefix_tree.search_best(bgp_msg['prefix'])
				if(prefix_node is not None):
					if(first_neighbor_asn not in prefix_node.data['neighbors']):
						## Trigger hijack


						print("HIJACK TYPE 1 detected!")
						return True
			return False

		except:
			print("Error on detect 1 hop neighbor hijack.")
