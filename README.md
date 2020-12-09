[![Python package](https://github.com/sreichholf/python-dreamboxapi/workflows/Python%20package/badge.svg?branch=master)](https://github.com/sreichholf/python-dreamboxapi/actions)

[![PyPi](https://img.shields.io/pypi/v/dreamboxapi.svg)](https://pypi.python.org/pypi/dreamboxapi)

### A python client library for dreamboxes using requests

### Super simple example
``` { .py }
from dreamboxapi.api import DreamboxApi
api = DreamboxApi(host="my.dreambox.local")
print(api.current.name)
```
