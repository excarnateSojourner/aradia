class Response:
	def __init__(self, status, headers=None, body=None):
		self.status = status
		self.successful = self.status < 400
		if self.successful:
			self.headers = headers or {}
		self.body = body or ''
