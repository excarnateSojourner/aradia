import datetime
import http.server as hs
from http import HTTPStatus
import importlib
import os
import re
from sys import argv
import urllib.parse

# The IP and port on which to serve.
SERVER_ADDRESS = ('192.168.0.19', 5000)
# The server should only serve files in this directory.
LIVE_DIR = 'live'
# All Python programs that handle POST requests should be in this directory. Assumed to be a child of LIVE_DIR.
POST_DIR = 'post'
LOG_FILE_PATH = 'log.txt'
# Specifies which request headers will be written to the log file for each request.
HEADERS_TO_LOG = ['user-agent', 'referer', 'content-type', 'content-length']
# When a request is logged, the body will be truncated to this length.
LOG_REQUEST_BODY_LEN = 200

def serve():
	os.chdir(LIVE_DIR)
	with hs.HTTPServer(SERVER_ADDRESS, AradiaRequestHandler) as httpd:
		print(f'Serving {LIVE_DIR}/ at {SERVER_ADDRESS[0]}:{SERVER_ADDRESS[1]}.')
		try:
			httpd.serve_forever()
		except KeyboardInterrupt:
			print('\nExiting.')
			raise SystemExit(0)

class AradiaRequestHandler(hs.SimpleHTTPRequestHandler):
	def do_GET(self):
		self.request_time = self.timestamp()
		self.parameters = {}
		# If a directory with no index.html was requested, reject.
		if self.path[-1] == '/' and not os.path.isfile(f'{self.path[1:]}index.html'):
			self.send_error(HTTPStatus.FORBIDDEN, message='This server does not give directory listings')
		# If a Python program meant to handle POST requests was requested, reject.
		elif self.path.startswith(f'/{POST_DIR}/'):
			self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
		else:
			super().do_GET()
	
	def do_POST(self):
		'''
		Runs Python programs in POST_DIR.
		The parameters in the request body are parsed into a dict of lists by urllib.parse.parse_qs(keep_blank_values=True) and saved as self.parameters. This entire AradiaRequestHandler is then passed to the Python program's main() function. (This gives the program access to things like the client_address, headers.get('referer'), and the request_time in addition to the parameters sent in the request.) The Python program is *not* expected to modify any part of this handler, nor call any non-static methods of this handler, nor write directly to self.wfile.
		The Python program is expected to return a 3-tuple representing either a successful response or an error response.
		0. A successful response consists of:
			0. The HTTP status code, either 1xx, 2xx, or 3xx, to include in the response (int).
			1. Headers to include in the response (dict).
			2. The response body (str). May be the empty string, but *not* None.
		1. An error response consists of:
			0. The HTTP status code, either 4xx or 5xx, to include in the response (int).
			1. A short, human-readable description of the error (str), or None.
			2. A longer description of the error which will be formatted as the response body (str), or None.
		'''
		self.request_time = self.timestamp()
		self.parameters = {}
		path_match = re.fullmatch(f'(/{POST_DIR}/[a-zA-Z0-9_\\-/]+)\\.py', self.path)
		if path_match:
			if os.path.isfile(self.path[1:]):
				# Even though the working directory is LIVE_DIR, importlib.import_module imports relative to the program that it is called in.
				program = f'{LIVE_DIR}{path_match[1]}'.replace('/', '.')
				# It took me *way* too long to realize that read() *needs* a length here.
				request_body = self.rfile.read(int(self.headers.get('content-length'))).decode()
				self.parameters = urllib.parse.parse_qs(request_body, keep_blank_values=True)
				module = importlib.import_module(program)
				response_values = module.main(self)
				# Successful response.
				if response_values[0] < 400:
					self.send_response(HTTPStatus(response_values[0]))
					for keyword, value in response_values[1].items():
						self.send_header(keyword, value)
					self.end_headers()
					self.wfile.write(response_values[2].encode())
				# Error response.
				else:
					self.send_error(HTTPStatus(response_values[0]), message=response_values[1], explain=response_values[2])
			else:
				self.send_error(HTTPStatus.NOT_FOUND)
		# Requested file outside of POST_DIR.
		else:
			self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
	
	def log_request(self, code='-', size='-'):
		LOG_SEPARATOR = ' | '
		message = (LOG_SEPARATOR.join([self.request_time, f'{self.client_address[0]}:{self.client_address[1]}', self.requestline, str(code.value)]) + '\n'
		+ LOG_SEPARATOR.join(f'{header}: {self.headers[header]}' for header in HEADERS_TO_LOG if header in self.headers) + '\n'
		+ LOG_SEPARATOR.join(f'{param}: {str(self.parameters[param])[:LOG_REQUEST_BODY_LEN]}' for param in self.parameters) + '\n'
		+ '#' * 20)
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
		with open(f'../{LOG_FILE_PATH}', 'a') as log_file:
			log_file.write(f'{message}\n' + ('#' * 20) + '\n')
	
	@staticmethod
	def timestamp():
		'''Returns the current time UTC time (with seconds but not milliseconds) in ISO format.'''
		return datetime.datetime.now(tz=datetime.timezone.utc).isoformat().split('.', maxsplit=1)[0]

if __name__ == '__main__':
	serve()
