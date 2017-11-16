import radix
from taps.ripe_ris import RIPEris
from taps.exabgp_client import ExaBGP
from taps.bgpmon import BGPmon
from multiprocessing import Process, Queue

class Monitor():

	prefix_tree = radix.Radix()
	process_ids = list()

	def __init__(self, configs, raw_log_queue, monitors):
		self.configs_ = configs
		self.raw_log_queue = raw_log_queue
		self.monitors = monitors
		self.init_monitor()


	def init_monitor(self):

		for config in self.configs_:
			try:
				for prefix in self.configs_[config]['prefixes']:
					node = self.prefix_tree.add(prefix.with_prefixlen)
					node.data["origin_asns"] = self.configs_[config]['origin_asns']
					node.data["neighbors"] = self.configs_[config]['neighbors']
					node.data["mitigation"] = self.configs_[config]['mitigation']
			except:
				print("Error on Monitor module.\n")

		prefixes = self.prefix_tree.prefixes()

		# Code here later to implement filter of monitors
		#self.init_ris_instances(prefixes)
		#self.init_bgpmon_instance(prefixes)
		self.init_exabgp_instance(prefixes)


	def init_ris_instances(self, prefixes):
		try:
			for prefix in prefixes:
				for ris_monitor in self.monitors['riperis']:
					p = Process(target=RIPEris, args=("", ris_monitor, self.raw_log_queue))
					p.start()
					self.process_ids.append(('RIPEris', p))				
		except:
			print("Error on initializing of RIPEris monitors.")


	def init_bgpmon_instance(self, prefixes):
		try:
			if(len(self.monitors['bgpmon']) == 1):
				p = Process(target=BGPmon, args=(self.prefix_tree, self.raw_log_queue, self.monitors['bgpmon'][0]))
				p.start()
				self.process_ids.append(('BGPmon', p))				
		except:
			print("Error on initializing of BGPmon.")


	def init_exabgp_instance(self, prefixes):
		try:
			if(len(self.monitors['exabgp']) > 0):
				for exabgp_monitor in self.monitors['exabgp']:
					prefixes = self.prefix_tree.prefixes()
					p = Process(target=ExaBGP, args=(prefixes, self.raw_log_queue, exabgp_monitor))
					p.start()
					self.process_ids.append(('ExaBGP', p))				
		except:
			print("Error on initializing of ExaBGP.")


	def get_process_ids(self):
		return self.process_ids
