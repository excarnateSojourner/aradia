# Aradia

import argparse
import datetime
import functools
import http.server
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

GET_EXCEPTIONS = {'favicon.ico': HTTPResponse(HTTPStatus.GONE)}
POST_EXCEPTIONS = {}
DEFAULT_HEADERS = ['user-agent', 'referer', 'content-type', 'content-length']
CWD = os.path.dirname(os.path.realpath(__file__))

def main():
	parser = argparse.ArgumentParser()
	parser.add_argument('address', help='The IP address to serve on.')
	parser.add_argument('port', type=int, help='The port to serve on.')
	parser.add_argument('-l', '--live-path', default='live', help='The path of the directory containing the files to serve. This directory must exist.')
	parser.add_argument('-s', '--scripts-path', default='scripts', help='The subpath of the directory of scripts that should handle post requests, within the directory of files to serve.')
	parser.add_argument('-o', '--log-path', default='aradia.log', help='The path of the log file in which to record requests.')
	parser.add_argument('-p', '--last-post-time-path', default='last_post_time.int', help='The path of the file in which to save the time of the last POST request.')
	parser.add_argument('-e', '--log-headers', nargs='+', default=DEFAULT_HEADERS, help='The list of request headers to log.')
	parser.add_argument('-r', '--log-request-len', default=200, type=int, help='The length to which requests should be truncated when logging them.')
	args = parser.parse_args()

	os.chdir(f'{CWD}/{args.live_path}')
	request_handler_args = vars(args).copy()
	for arg in ['address', 'port']:
		del request_handler_args[arg]
	with http.server.HTTPServer((args.address, args.port), functools.partial(AradiaRequestHandler, **request_handler_args)) as httpd:
		print(f'Serving {args.live_path}/ at {args.address}:{args.port}.')
		try:
			httpd.serve_forever()
		except KeyboardInterrupt:
			print('\nExiting.')
			raise SystemExit(0)

class AradiaRequestHandler(http.server.SimpleHTTPRequestHandler):
	def __init__(self, request, client_address, server, live_path='live', scripts_path='scripts', log_path='aradia.log', last_post_time_path='last_post_time.int', log_headers=DEFAULT_HEADERS, log_request_len=200):
		self.live_path = live_path
		self.scripts_path = scripts_path
		self.log_path = log_path
		self.last_post_time_path = last_post_time_path
		super().__init__(request, client_address, server)

	def do_GET(self):
		# If a Python program meant to produce requests was requested, reject.
		if self.path.startswith(f'/{self.scripts_path}/'):
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
		Runs Python programs in self.scripts_path.
		The parameters in the request body are parsed into a dict of lists by urllib.parse.parse_qs(keep_blank_values=True) and saved as self.parameters. This entire AradiaRequestHandler is then passed to the Python program's main() function. (This gives the program access to things like the client_address, headers.get('referer'), and the last_post_time in addition to the parameters sent in the request.) The Python program is *not* expected to modify any part of this handler, nor call any non-static methods of this handler, nor write directly to self.wfile. Doing so results in undefined behaviour.
		'''

		path_match = re.fullmatch(f'(/{self.scripts_path}/[a-zA-Z0-9_\\-/]+)\\.py', self.path)
		with open('../' + self.last_post_time_path) as last_post_time_file:
			last_post_time = int(last_post_time_file.read()[:-1])
		if int(time.time()) - last_post_time < 15:
			self.send_error(HTTPStatus.TOO_MANY_REQUESTS, explain='You must wait a minimum of 15 seconds between POST requests. Use your browser\'s back button and try again after waiting')
		elif not path_match:
			self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
		elif not os.path.isfile(self.path[1:]):
			self.send_error(HTTPStatus.NOT_FOUND)
		# Good request.
		else:
			with open('../' + self.last_post_time_path, 'w') as last_post_time_file:
				last_post_time_file.write(str(int(time.time())) + '\n')
			# Even though the working directory is self.live_path, importlib.import_module imports relative to the program that it is called in.
			program = f'{self.live_path}{path_match[1]}'.replace('/', '.')
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
			message += log_separator.join(f'{header}: {value}' for header, value in self.headers.items() if header in self.log_headers) + '\n'
		except AttributeError:
			pass
		try:
			message += log_separator.join(f'{param}: {value[:self.log_request_len]}' for param, value in self.parameters.items())
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
		with open('../' + self.log_path, 'a') as log_file:
			log_file.write(f'{message}\n{"#" * 20}\n')

if __name__ == '__main__':
	main()
