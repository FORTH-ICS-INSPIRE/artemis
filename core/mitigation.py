import sys, os
from os.path import expanduser
from core.deaggregate import Deaggr
from netaddr import IPNetwork


HOME = expanduser("~")
MITIGATION_SCRIPTS_DIR = "{}/artemis-tool/routers/quagga".format(HOME)
PY_BIN = '/usr/bin/python'
QC_PY = '{}/quagga_command.py'.format(MITIGATION_SCRIPTS_DIR)
MTS_PY = '{}/moas_tcp_sender.py'.format(MITIGATION_SCRIPTS_DIR)


class Mitigation():

	def __init__(self, prefix_node=None, bgp_msg=None, local_mitigation=None, moas_mitigation=None):

		# TODO: check if we need also "type" differentiation (e.g., quagga, etc.)
		self.prefix_node = prefix_node
		self.bgp_msg = bgp_msg
		self.local_mitigation = local_mitigation
		self.moas_mitigation = moas_mitigation

		self.init_mitigation()


	def init_mitigation(self):
		try:

			if IPNetwork(self.bgp_msg['prefix']).prefixlen < 24:

				if 'deaggregate' in self.prefix_node.data['mitigation']:

					self.deaggregate_prefix(
						prefix=self.bgp_msg['prefix'],
						local_asn=self.local_mitigation['asn'],
						local_telnet_ip=self.local_mitigation['ip'],
						local_telnet_port=self.local_mitigation['port'])

				elif 'outsource' in self.prefix_node.data['mitigation']:

					self.announce_prefix(
						prefix=self.bgp_msg['prefix'],
						local_asn=self.local_mitigation['asn'],
						local_telnet_ip=self.local_mitigation['ip'],
						local_telnet_port=self.local_mitigation['port'])

					self.moas_outsource(
						prefix=self.bgp_msg['prefix'],
						moas_asn=self.moas_mitigation['asn'],
						moas_ip=self.moas_mitigation['ip'],
						moas_port=self.moas_mitigation['port']
					)

				else:

					print('[MITIGATION] Resolving hijack manually!')
			else:

				if 'deaggregate' in self.prefix_node.data['mitigation']:

					print('[MITIGATION] Cannot deaggregate prefix {} due to filtering!'.format(self.bgp_msg['prefix']))

				if 'outsource' in self.prefix_node.data['mitigation']:

					self.announce_prefix(
						prefix=self.bgp_msg['prefix'],
						local_asn=self.local_mitigation['asn'],
						local_telnet_ip=self.local_mitigation['ip'],
						local_telnet_port=self.local_mitigation['port'])

					self.moas_outsource(
						prefix=self.bgp_msg['prefix'],
						moas_asn=self.moas_mitigation['asn'],
						moas_ip=self.moas_mitigation['ip'],
						moas_port=self.moas_mitigation['port']
					)

				else:

					print('[MITIGATION] Resolving hijack manually!')
		except:

			print("[MITIGATION] Invalid prefix '{}'!".format(self.bgp_msg['prefix']))


	def announce_prefix(self, prefix=None, local_asn=None, local_telnet_ip=None, local_telnet_port=None):
		os.system('{} {} -th {} -tp {} -la {} -ap {}'.format(
			PY_BIN,
			QC_PY,
			local_telnet_ip,
			local_telnet_port,
			local_asn,
			prefix))


	def deaggregate_prefix(self, prefix = None, local_asn=None, local_telnet_ip=None, local_telnet_port=None):
		deaggr_prefixes = Deaggr(prefix, 24).get_subprefixes()
		if len(deaggr_prefixes) > 0:
			for deagg_prefix in deaggr_prefixes:
				self.announce_prefix(
					prefix=deagg_prefix,
					local_asn=local_asn,
					local_telnet_ip=local_telnet_ip,
					local_telnet_port=local_telnet_port)


	def moas_outsource(self, prefix = None, moas_asn=None, moas_ip=None, moas_port=None):
		os.system('{} {} -r {} -p {} -m {}'.format(
			PY_BIN,
			MTS_PY,
			moas_ip,
			moas_port,
			prefix))


