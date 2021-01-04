#!/usr/bin/env python3
from ctf_gameserver.checkerlib import BaseChecker, CheckResult
from ctf_gameserver import checkerlib

import logging
import random
import nclib

values = [
	"Normal",
	"Critical",
	"Needs investigation"
]

def random_sensor_data():
	width = random.randint(10, 20)
	height = random.randint(10, 20)
	return "Sector " + hex(random.randint(0,256)) + ";" + \
		"Width: " + str(width) + ";" + \
		"Height: " + str(height) + ";" + \
		"Status: " + random.choice(values) + ";" + \
		"Height data: " + "".join([chr(random.randint(ord('a'), ord('z'))) for i in range(width * height)])

class CheckerException(Exception):
	def __init__(self, code, what):
		super().__init__(what)
		self.code = code

class CartographyChecker(BaseChecker):
	def connect(self):
		try:
			logging.info("Connecting...")
			conn = nclib.Netcat((self.ip, 6666), raise_timeout=True)
			conn.settimeout(2)
			return conn
		except nclib.NetcatError:
			logging.info("Failed to connect to [{}]:6666".format(self.ip))

	def new_sector(self, conn, size):
		conn.sendline(b'0')
		conn.recv_until(b"Enter the sector's size:\n")
		conn.sendline(str(size).encode("ASCII"))
		logging.info("Created sector of size: %d" % size)

	def fill_sector(self, conn, pos, data):
		conn.sendline(b'1')
		conn.recv_until(b"Where do you want to write?\n")
		conn.sendline(str(pos).encode("UTF-8"))
		conn.recv_until(b"How much do you want to write?\n")
		conn.sendline(str(len(data)).encode("UTF-8"))
		conn.recv_until(b"Enter your sensor data:\n")
		conn.sendline(data.encode("UTF-8"))
		logging.info("Filled sector with data")

	def read_sector(self, conn, pos, length):
		conn.sendline(b'2')
		conn.recv_until(b"Where do you want to read?\n")
		conn.sendline(str(pos).encode("UTF-8"))
		conn.recv_until(b"How much do you want to read?\n")
		conn.sendline(str(length).encode("UTF-8"))

		data = conn.recv_until(b"\n")[:-1].decode("UTF-8")
		if len(data) != length:
			logging.error("Service returned data of length %d but expected length %d" % (len(data), length))
			raise CheckerException(CheckResult.FAULTY, "Not working")

		if data == "Invalid range":
			logging.error("Failed to read: Range %d to %d is invalid (according to service)" % (pos, pos + length))
			raise CheckerException(CheckResult.FAULTY, "Not working")

		logging.info("Read data from sector")
		return data

	def save_sector(self, conn):
		conn.sendline(b'3')
		conn.recv_until(b"Saved sector as ")

		data = conn.recv_until(b"\n").decode("UTF-8")[1:-2]
		logging.info("Saved sector as %s" % data)

		return data

	def load_sector(self, conn, name):
		conn.sendline(b'4')
		conn.recv_until(b"Enter sector name:\n")
		conn.sendline(name.encode("UTF-8"))

		response = conn.recv_until(b"\n").decode("UTF-8")
		res = response == "Sector loaded\n"
		if res:
			logging.info("Loaded sector")
		else:
			logging.error("Failed to load sector: %s" % response)
		return res

	def place_flag(self, tick):
		# get the flag for the current tick
		flag = checkerlib.get_flag(tick)
		logging.info("Trying to place flag %s for tick %d" % (flag, tick))
		conn = self.connect()
		if not conn:
			return CheckResult.DOWN

		try:
			self.new_sector(conn, len(flag))
			self.fill_sector(conn, 0, flag)
			sector = self.save_sector(conn)
			checkerlib.store_state(str(tick), {'sector':sector})
			logging.info("Succeeded storing flag")
		except CheckerException as e:
			logging.error("Failed to place flag: %s" % str(e))
			return e.code
		except nclib.NetcatTimeout:
			logging.error("Failed to place flag: Timeout while reading")
			return CheckResult.FAULTY
		except UnicodeDecodeError:
			logging.error("Invalid UTF8")
			return CheckResult.FAULTY
		except nclib.NetcatError:
			logging.error("Failed to place flag: NetcatError")
			return CheckResult.DOWN
		finally:
			conn.close()

		return CheckResult.OK # everything went well

	# checks if this flag is available
	def check_flag(self, tick):
		# get our pwd for this tick
		state = checkerlib.load_state(str(tick))
		if not state or not 'sector' in state:
			return CheckResult.FLAG_NOT_FOUND
		sector = state['sector']

		flag_expected = checkerlib.get_flag(tick)
		logging.info("Checking if flag %s from tick %d is still present" % (flag_expected, tick))

		conn = self.connect()
		if not conn:
			return CheckResult.DOWN

		try:
			if not self.load_sector(conn, sector):
				logging.error("Couldn't load sector '%s' where flag is stored" % sector)
				return CheckResult.FLAG_NOT_FOUND

			flag_found = self.read_sector(conn, 0, len(flag_expected))
			if flag_found != flag_expected:
				logging.error("Expected flag '%s', found '%s'" % (flag_expected, flag_found))
				return CheckResult.FLAG_NOT_FOUND

			logging.info("Flag found")
			return CheckResult.OK # flag found
		except nclib.NetcatTimeout:
			logging.error("Failed to check flag: Timeout while reading")
			return CheckResult.FAULTY
		except UnicodeDecodeError:
			logging.error("Invalid UTF8")
			return CheckResult.FAULTY
		except nclib.NetcatError:
			logging.error("Failed to check flag: NetcatError")
			return CheckResult.DOWN
		finally:
			conn.close()

	# checks if the intended functionality of the service is working
	def check_service(self):
		logging.info("Checking service availability...")
		conn = self.connect()
		if not conn:
			return CheckResult.DOWN
		
		try:
			# Try either a payload that makes sense
			# Or just a random one
			if random.choice([True, False]):
				payload = random_sensor_data()
				logging.info("with a structured payload")
			else:
				rand_size = random.randint(10, 100)
				payload = "".join([chr(random.randint(ord('a'), ord('z'))) for i in range(rand_size)])
				logging.info("with a random payload")

			self.new_sector(conn, len(payload))
			self.fill_sector(conn, 0, payload)

			logging.info("Querying substrings to check if they match")
			for i in range(5):
				start = random.randint(0, len(payload) - 1)
				length = random.randint(1, len(payload) - start)
				expected = payload[start:start+length]
				data = self.read_sector(conn, start, length)
				if data != expected:
					logging.error("Failed to get substring, expected '%s', got '%s'" % (expected, data))
					return CheckResult.FAULTY

			logging.info("Saving the sector...")
			sector = self.save_sector(conn)
			logging.info("Loading it...")
			if not self.load_sector(conn, sector):
				logging.error("Failed to load just saved sector %s" % sector)
				return CheckResult.FAULTY
			logging.info("Done")
			return CheckResult.OK
		except CheckerException as e:
			logging.error("Failed to check service: %s" % str(e))
			return e.code
		except nclib.NetcatTimeout:
			logging.error("Failed to check service: Timeout while reading")
			return CheckResult.FAULTY
		except UnicodeDecodeError:
			logging.error("Invalid UTF8")
			return CheckResult.FAULTY
		except nclib.NetcatError:
			logging.error("Failed to check service: NetcatError")
			return CheckResult.DOWN
		finally:
			conn.close()

if __name__ == '__main__':
	checkerlib.run_check(CartographyChecker)
