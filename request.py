import http

class HTTPResponse:
	def __init__(self, status, headers=None, body=None):
		'''
		The Python program is expected to return a 3-tuple representing either a successful response or an error response.
		0. A successful response consists of:
			0. The HTTP status code, either 1xx, 2xx, or 3xx, to include in the response (int).
			1. Headers to include in the response (dict).
			2. The response body (str). May be the empty string, but *not* None.
		1. An error response consists of:
			0. The HTTP status code, either 4xx or 5xx, to include in the response (int).
			1. A description of the error which will be formatted as the response body (str), or None.
		'''
		self.status = status
		self.successful = self.status < 400
		if self.successful:
			self.headers = headers
		self.body = body

	def send(self, request_handler):
		if self.successful:
			request_handler.send_response(http.HTTPStatus(self.status))
			for keyword, value in self.headers.items():
				request_handler.send_header(keyword, value)
			request_handler.end_headers()
			request_handler.wfile.write(self.body.encode())
		else:
			self.send_error(self.status, self.body)
