import sys, os
from os.path import expanduser
from deaggregate import Deaggr


HOME = expanduser("~")
MITIGATION_SCRIPTS_DIR = "{}/artemis/mininet".format(HOME)
PY_BIN = '/usr/bin/python'
QC_PY = '{}/quagga_command.py'.format(MITIGATION_SCRIPTS_DIR)
MTS_PY = '{}/moas_tcp_sender.py'.format(MITIGATION_SCRIPTS_DIR)


class Mitigation():

	def __init__(self,
				 prefix_node=None,
				 bgp_msg=None,
				 local_mitigation=None,
				 moas_mitigation=None):

		print(str(prefix_node.prefix))
		print(str(prefix_node.data))
		print(str(bgp_msg))
		print(str(local_mitigation))
		print(str(moas_mitigation))

	def init_mitigation(self):

		# pseudocode
		# if less specific than /24 prefix:
		# 	if deaggregate enabled:
		# 		deaggregate locally
		#   elif outsource enabled:
		#   	announce prefix as is locally and get help
		#   else:
		# 		do nothing (manual resolution)
		# elif /24 prefix:
		# 	if outsource enabled:
		# 		announce /24 and get MOAS help
		# 	else:
		# 		do nothing (manual resolution)
		# else:
		# 	if outsource enabled:
		# 		announce /24 and get MOAS help
		# 	else:
		# 		do nothing (manual resolution)

		pass

	def announce_prefix(self,
						local_asn=None,
						local_telnet_ip=None,
						local_telnet_port=None):

		os.system('{} {} -th {} -tp {} -la {} -ap {}'.format(PY_BIN,
															 QC_PY,
															 local_telnet_ip,
															 local_telnet_port,
															 local_asn,
															 deagg_prefix))


	def deaggregate(self,
					prefix = None,
					local_asn=None,
					local_telnet_ip=None,
					local_telnet_port=None):

		deaggr_prefixes = Deaggr(prefix, 24)
		if len(deaggr_prefixes) > 0:
			for deagg_prefix in deaggr_prefixes:
				self.announce_prefix(local_asn=local_asn,
									 local_telnet_ip=local_telnet_ip,
									 local_telnet_port=local_telnet_port)


	def moas_outsource(self,
					   prefix = None,
					   moas_asn=None,
					   moas_ip=None,
					   moas_port=None):

		os.system('{} {} -r {} -p {} -m {}'.format(PY_BIN,
												   MTS_PY,
												   moas_ip,
												   moas_port,
												   moas_prefix))


