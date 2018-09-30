

class Config():

	def __init__(self, raw_config):
		self.raw_config = raw_config
		self.prefixes_list = []
		
		self.parse_config()

	def parse_config(self): 
		self.create_prefix_list()

	def create_prefix_list(self):
		if 'prefixes' in self.raw_config:
			for group_of_prefixes in self.raw_config['prefixes']:
				for prefix in  self.raw_config['prefixes'][group_of_prefixes]:
					self.prefixes_list.append(prefix)

	def get_prefixes_list(self):
		return self.prefixes_list

	def get_raw_config(self):
		return self.raw_config


