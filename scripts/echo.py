from response import Response

def main(request_handler):
	return Response(200, body=request_handler.parameters['message'][0])
