# Aradia

import datetime
import http.server as hs
from http import HTTPStatus
import importlib
import os
import os.path
import re
from request import HTTPResponse
import sys
import time
import traceback
import urllib.parse

# The IP and port on which to serve.
SERVER_ADDRESS = ('192.168.0.19', 5000)
# All other paths are relative to the location of this program.
CWD = os.path.dirname(os.path.realpath(__file__))
# The server should only serve files and run scripts in this directory.
LIVE_DIR = 'live'
# All Python programs that handle POST requests should be in this directory. Assumed to be a child of LIVE_DIR.
SCRIPT_DIR = 'scripts'
# Assumed to be a sibling of this program.
LOG_PATH = 'log.log'
LAST_POST_TIME_PATH = 'last_post_time.int'
# Specifies which request headers will be written to the log file for each request.
HEADERS_TO_LOG = ['user-agent', 'referer', 'content-type', 'content-length']
# When a request is logged, the body will be truncated to this length.
LOG_REQUEST_BODY_LEN = 200

GET_EXCEPTIONS = {'favicon.ico': HTTPResponse(HTTPStatus.GONE)}
POST_EXCEPTIONS = {}

def serve():
	os.chdir(f'{CWD}/{LIVE_DIR}')
	with hs.HTTPServer(SERVER_ADDRESS, AradiaRequestHandler) as httpd:
		print(f'Serving {LIVE_DIR}/ at {SERVER_ADDRESS[0]}:{SERVER_ADDRESS[1]}.')
		try:
			httpd.serve_forever()
		except KeyboardInterrupt:
			print('\nExiting.')
			raise SystemExit(0)

class AradiaRequestHandler(hs.SimpleHTTPRequestHandler):
	def do_GET(self):
		# If a Python program meant to produce requests was requested, reject.
		if self.path.startswith(f'/{SCRIPT_DIR}/'):
			self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
		# If a directory with no index.html was requested, reject.
		elif self.path.endswith('/') and not os.path.isfile(self.path[1:] + 'index.html'):
			self.send_error(HTTPStatus.FORBIDDEN, explain='This server does not give directory listings')
		# If the '.html' has been omitted, add it automatically.
		elif not os.path.exists(self.path[1:]) and '.' not in self.path.rsplit('/', maxsplit=1)[-1] and os.path.isfile(self.path[1:] + '.html'):
			self.send_response(HTTPStatus.MOVED_PERMANENTLY)
			self.send_header('Location', self.path + '.html')
			self.end_headers()
		else:
			super().do_GET()

	def do_POST(self):
		'''
		Runs Python programs in SCRIPT_DIR.
		The parameters in the request body are parsed into a dict of lists by urllib.parse.parse_qs(keep_blank_values=True) and saved as self.parameters. This entire AradiaRequestHandler is then passed to the Python program's main() function. (This gives the program access to things like the client_address, headers.get('referer'), and the last_post_time in addition to the parameters sent in the request.) The Python program is *not* expected to modify any part of this handler, nor call any non-static methods of this handler, nor write directly to self.wfile. Doing so results in undefined behaviour.
		'''

		path_match = re.fullmatch(f'(/{SCRIPT_DIR}/[a-zA-Z0-9_\\-/]+)\\.py', self.path)
		with open('../' + LAST_POST_TIME_PATH) as last_post_time_file:
			last_post_time = int(last_post_time_file.read()[:-1])
		if int(time.time()) - last_post_time < 15:
			self.send_error(HTTPStatus.TOO_MANY_REQUESTS, explain='You must wait a minimum of 15 seconds between POST requests. Use your browser\'s back button and try again after waiting')
		elif not path_match:
			self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
		elif not os.path.isfile(self.path[1:]):
			self.send_error(HTTPStatus.NOT_FOUND)
		# Good request.
		else:
			with open('../' + LAST_POST_TIME_PATH, 'w') as last_post_time_file:
				last_post_time_file.write(str(int(time.time())) + '\n')
			# Even though the working directory is LIVE_DIR, importlib.import_module imports relative to the program that it is called in.
			program = f'{LIVE_DIR}{path_match[1]}'.replace('/', '.')
			request_body = self.rfile.read(int(self.headers.get('content-length'))).decode()
			self.parameters = urllib.parse.parse_qs(request_body, keep_blank_values=True)
			module = importlib.import_module(program)
			try:
				response_values = module.main(self)
			except:
				response_values = 500, None, None
				self.log_message(traceback.format_exc(limit=10))
			# Successful response.
			if response_values[0] < 400:
				self.send_response(HTTPStatus(response_values[0]))
				for keyword, value in response_values[1].items():
					self.send_header(keyword, value)
				self.end_headers()
				self.wfile.write(response_values[2].encode())
			# Error response.
			else:
				self.send_error(HTTPStatus(response_values[0]), explain=response_values[1])

	def log_request(self, code='-', size='-'):
		log_separator = ' | '
		time_str = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
		message = log_separator.join((time_str[:time_str.index('.')], f'{self.client_address[0]}:{self.client_address[1]}', self.requestline, str(code.value))) + '\n'
		try:
			message += log_separator.join(f'{header}: {value}' for header, value in self.headers.items() if header in HEADERS_TO_LOG) + '\n'
		except AttributeError:
			pass
		try:
			message += log_separator.join(f'{param}: {value[:LOG_REQUEST_MAX_VALUE_LEN]}' for param, value in self.parameters.items())
		except AttributeError:
			pass
		self.log_message(message)

	def log_message(self, message, *args):
		'''
		Logs an arbitrary message to the log file.
		If args are given, messages is a str to format, printf-style, with args, and then log. Otherwise, messages is a str to log. The printf-style formatting is supported only because http.server.BaseHTTPRequestHandler.log_message() provides it, and AradiaRequestHandler does not override all methods that call BaseHTTPRequestHandler.log_message(). If args are provided and len(args) does not match the formatting in message, message is logged unformatted.
		'''

		if args:
			try:
				message = message % args
			except TypeError:
				pass
		with open('../' + LOG_PATH, 'a') as log_file:
			log_file.write(f'{message}\n{"#" * 20}\n')

if __name__ == '__main__':
	serve()
