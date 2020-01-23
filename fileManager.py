# Listens on port 5000 for requests, authenticates them, and changes the files that are served by the http.server server accordingly.

from socket import AF_INET, SOCK_STREAM, socket
import os
import traceback

PORT = 5000

def main():
	with open('../auth.txt') as authFile:
		authHash = authFile.read()[:-1]

	parentSocket = socket(AF_INET, SOCK_STREAM)
	binded = False
	while not binded:
		try:
			parentSocket.bind(('', 5000))
			binded = True
		except OSError:
			# DEBUG.
			PORT += 1

	parentSocket.listen(2)
	print(f'Listening on port {PORT}.')

	while True:
		try:
			childSocket, _ = parentSocket.accept()
			# Max file size is 1 MB.
			header, authGiven, body = childSocket.recv(2 ** 20).decode().split('\n\n', maxsplit=2)
			header = header.replace('../', '').split(maxsplit=2)
			if header[0] == 'POST' and header[1] == '/git':
				if authGiven == authHash:
					request = header[1][1:].split('?', maxsplit=1)
					if request[0] == 'mkdir':
						try:
							os.mkdir(request[1])
							clientSocket.send('HTTP/1.1 200 OK\n\n'.encode())
						except OSError as err:
							clientSocket.send(f'HTTP/1.1 500 Internal Server Error\n\n{traceback.format_tb(err)}'.encode())
					elif request[0] == 'rm':
					try:
						# Open and truncate the file, creating it if it does not exist.
						with open(header[1], 'w') as f:
							f.write(body)
					except FileNotFoundError:
						print('File not found...')
						childSocket.send('HTTP/1.1 404 Not Found\n\n'.encode())
				else:
					print('Authentication failed.')
					childSocket.send('HTTP/1.1 403 Forbidden\n\n'.encode())
			elif header[0] == 'GET' and header[1] == '/list':
				# Return the tree structure of all subdirectories and files.
				childSocket.send(tree.encode())
			else:
				print('Received non-POST request.')
				childSocket.send('HTTP/1.1 400 Bad Request\n\n'.encode())
		except KeyboardInterrupt:
			parentSocket.close()
			childSocket.close()
			raise
		except Exception as err:
			traceback.print_tb(err.__traceback__)

if __name__ == '__main__':
	main()
