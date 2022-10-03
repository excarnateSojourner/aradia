def main(request_handler):
	return 200, {}, request_handler.parameters['message'][0]
