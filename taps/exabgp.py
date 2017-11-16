from socketIO_client import SocketIO
import ipaddress
#from core.files import WriteLogs

import sys

class ExaBGP():

	socketIO = None
	config = {'host': None, 'prefix': None}

	def __init__(self, prefixes, raw_log_queue, address_port):

		self.config['host'] = str(address_port[0]) + ":" + str(address_port[1])
		self.config['prefixes'] = prefixes
		
		self.write2file = WriteLogs('ExaBGP', host, "all_prefixes")

		self.raw_log_queue = raw_log_queue
		self.start_loop()


	def start_loop(self):
		while(True):
			self.start()


	def start(self):
		socketIO = SocketIO("http://" + str(self.config['host']))
		print("[ExaBGP] %s monitor service is up for prefix %s" % (self.config['host'],  self.config['prefix']))


		def on_connect(*args):
			prefixes_ = {"prefixes": self.config['prefixes']}
			socketIO.emit("exa_subscribe", prefixes_)


		def on_pong(*args):
			socketIO.emit("ping")

		def exabgp_msg(bgp_message):
			
			# Write raw log
			self.write2file.append_log(bgp_message)

			print(bgp_message)
			# Put in queue to be tranformed to Pformat
			self.raw_log_queue.put(('ExaBGP', self.config['host'], bgp_message))

			#socketIO.emit("ping")


		def on_reconnecting():
			print("ExaBGP host ", self.config['host'], " reconnecting.")

		def on_reconnect_error():
			print("ExaBGP host ", self.config['host'], " reconnect error.")


		def on_disconnect():
			print("ExaBGP host ", self.config['host'], " disconnected.")
			socketIO.close()

		def on_error():
			print("ExaBGP host ", self.config['host'], " error.")

		socketIO.on("connect", on_connect)
		socketIO.on("disconnect", on_disconnect)
		#socketIO.on("pong", on_pong)
		socketIO.on("exa_message", exabgp_msg)
		#socketIO.on("reconnecting", on_reconnecting)
		#socketIO.on("reconnect_error", on_reconnect_error)
		#socketIO.on("error", on_error)

		socketIO.wait()



if __name__ == '__main__':

	router = sys.argv[1]
	prefix = sys.argv[2]
	instance = ExaBGP(router, prefix)
