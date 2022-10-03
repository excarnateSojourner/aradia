# Aradia
Aradia is a simple Python server I originally made for my own recreational use. It handles GET requests, and allows you to write your own Python scripts to handle POST requests, too.

## Security
The library it uses, Python's [http.server](https://docs.python.org/3/library/http.server.html), only performs basic security checks, and therefore is not recommended for production. So naturally Aradia is not, either.
