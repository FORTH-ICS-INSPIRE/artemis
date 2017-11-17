from pathlib import Path
import time
import json
import os

class WriteLogs():

	path = "logs/"

	def __init__(self, service, monitor, prefix="all"):

		## dd/mm/yyyy format
		self.date = time.strftime("%d-%m-%Y")
		self.service = service
		self.monitor = monitor
		self.prefix = prefix
		self.filename = str(monitor) + "_" + str(prefix) + "_" + str(self.date)
		if not os.path.isdir(self.path):
			os.mkdir(self.path)


	def set_filename(self, prefix):		
		self.filename = str(self.monitor) + "_" + str(prefix) + "_" + str(self.date)


	def set_date(self):
		self.date = time.strftime("%d-%m-%Y")

	def append_log(self, log_line):
		try:
			timestamp = int(time.time())
			with open(self.path + self.filename, "a") as file:
				file.write(str(timestamp) + ", " + json.dumps(log_line) + "\n")
			file.close()
		except:
			print("Failed to write log on file: " + self.path + self.filename)
