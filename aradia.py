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
import sys
import time
import traceback
import urllib.parse

from response import Response

GET_EXCEPTIONS = {'favicon.ico': Response(HTTPStatus.GONE)}
POST_EXCEPTIONS = {}
DEFAULT_HEADERS = ['user-agent', 'referer', 'content-type', 'content-length']
CWD = os.path.dirname(os.path.realpath(__file__))
UP = os.path.pardir + os.path.sep

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

	os.chdir(CWD + os.path.sep + args.live_path)
	if not os.path.exists(args.scripts_path):
		os.mkdir(args.scripts_path)
	full_time_path = UP + args.last_post_time_path
	if not os.path.exists(full_time_path):
		with open(full_time_path, 'w') as time_file:
			print('0', file=time_file)
	request_handler_args = {k: v for k, v in vars(args).items() if k not in ['address', 'port']}
	with http.server.HTTPServer((args.address, args.port), functools.partial(AradiaRequestHandler, **request_handler_args)) as httpd:
		print(f'Serving {args.live_path}{os.path.sep} at {args.address}:{args.port}.')
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
		# Remove initial slash.
		path = self.path[1:]
		if path in GET_EXCEPTIONS:
			self.send(GET_EXCEPTIONS[path])
		# If a Python program meant to produce requests was requested, reject.
		elif os.path.exists(path) and os.path.samefile(os.path.dirname(path), self.scripts_path):
			self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
		# If a directory with no index.html was requested, reject.
		elif (os.path.isdir(path) or not path) and not os.path.isfile(os.path.join(path, 'index.html')):
			self.send_error(HTTPStatus.FORBIDDEN, explain='This server does not give directory listings')
		# If the '.html' has been omitted, add it automatically and redirect.
		elif not os.path.exists(path) and not os.path.splitext(path)[1] and os.path.isfile(path + '.html'):
			self.send(Response(HTTPStatus.MOVED_PERMANENTLY, {'Location': path + '.html'}))
		else:
			super().do_GET()

	def do_POST(self):
		'''
		Runs Python programs in self.scripts_path.
		The parameters in the request body are parsed into a dict of lists and saved as self.parameters. This entire AradiaRequestHandler is then passed to the program's main() function. (This gives the program access to things like the client_address, headers.get('referer'), and the last_post_time in addition to the parameters sent in the request.) If the program is modifies any part of this handler (including by calling one of its non-static methods), undefined behaviour will occur.
		The Python program is expected to return a Response (as defined in response.py).
		'''

		# Remove initial slash.
		path = self.path[1:]
		if path in POST_EXCEPTIONS:
			self.send(POST_EXCEPTIONS[path])
		path_match = re.fullmatch(f'({self.scripts_path}{os.path.sep}[a-zA-Z0-9_\\-{os.path.sep}]+)\\.py', path)
		with open(UP + self.last_post_time_path) as last_post_time_file:
			last_post_time = int(last_post_time_file.read()[:-1])
		if int(time.time()) - last_post_time < 15:
			self.send_error(HTTPStatus.TOO_MANY_REQUESTS, explain='You must wait a minimum of 15 seconds between POST requests. Use your browser\'s back button and try again after waiting')
		elif not path_match:
			self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
		elif not os.path.isfile(path):
			self.send_error(HTTPStatus.NOT_FOUND)
		# Good request.
		else:
			with open(UP + self.last_post_time_path, 'w') as last_post_time_file:
				last_post_time_file.write(str(int(time.time())) + '\n')
			# Even though the working directory is self.live_path, importlib.import_module imports relative to the program that it is called in.
			program = f'{self.live_path}{os.path.sep}{path_match[1]}'.replace(os.path.sep, '.')
			request_body = self.rfile.read(int(self.headers.get('content-length'))).decode()
			self.parameters = urllib.parse.parse_qs(request_body, keep_blank_values=True)
			module = importlib.import_module(program)
			try:
				response = module.main(self)
			except:
				response = Response(500, body='The program called to handle the request raised an exception.')
				self.log_message(traceback.format_exc(limit=10))
			self.send(response)

	def send(self, res):
		if res.successful:
			self.send_response(http.HTTPStatus(res.status))
			for key, val in res.headers.items():
				self.send_header(key, val)
			self.end_headers()
			self.wfile.write(res.body.encode())
		else:
			self.send_error(res.status, explain=res.body)

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
		If args are given, messages is a str to format using str.format() on args, and then log. Otherwise, messages is a str to log. The printf-style formatting is supported only because http.server.BaseHTTPRequestHandler.log_message() provides it, and AradiaRequestHandler does not override all methods that call BaseHTTPRequestHandler.log_message(). If args are provided and len(args) does not match the formatting in message, message is logged unformatted.
		'''

		if args:
			try:
				message = message.format(args)
			except TypeError:
				pass
		with open(UP + self.log_path, 'a') as log_file:
			log_file.write(f'{message}\n{"#" * 20}\n')

if __name__ == '__main__':
	main()
