# About

This contains general structure and expected usage of the pycraft2 package.

## Packets

Packets are organized into folders based on the state of the client,
e.g. `handshaking`, `status`, `login`, and `play`.
Each packet is a child of `S2S_0xFF` which has helper methods for sending and querying packets.
The child packet will have three overridden attributes: `__doc__`, `_info()` and `_dataTypes()`.

- `__doc__` is a string that describes the packet, its purpose, and its structure.
- `_info()` is a method that returns a string with the packet's name, ID, and state in a dictionary.
- `_dataTypes()` is a method that returns a dictionary of the packet's fields and their data types.

The packets must have these three attributes overridden, and the packet must be a child of `S2S_0xFF`.
This is enforced in the `packet_test.py` pytest file.

In each folder, the `__init__.py` file will import all the packets in the folder,
so that they can be accessed from the folder's namespace.

# Connection

The `connector.py` file contains the `MCSocket` class which is an async class.
That means you MUST use `await` when initializing the class and when calling most of its methods.
The class is ment to be a high level interface for a minecraft server allowing you to easily perform actions.

Example usage:

```python
from pyutils.pycraft2.connector import MCSocket
import json


async def main():
    sock = await MCSocket(
        host=("localhost", 25565)
    )

    await sock.handshake_status(version_id=754)
    response = await sock.status_request()

    print(json.dumps(response, indent=2))
```

# Data Types

The encode and decode methods in `packet.py` have good explanations for each data type in their __doc__ strings.

# Version support

I only plan on supporting version after the netty rewrite, so 1.7.10 and up.
