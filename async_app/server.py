#!/usr/bin/env python

import asyncio
import json

# from pprint import pprint

FUNCTIONS = {}


def register(name: str):
    """Decorator to register functions callable from clients."""

    def decorator(fn):
        FUNCTIONS[name] = fn
        return fn

    return decorator


@register("add")
def add(a: int, b: int) -> int:
    return a + b


@register("upper")
def upper(s: str) -> str:
    return s.upper()


class RpcServerProtocol(asyncio.Protocol):
    def __init__(self):
        self.transport = None
        self._buffer = ""

    def connection_made(self, transport):
        peername = transport.get_extra_info("peername")
        print(f"Connetion from {peername}")
        self.transport = transport

    def data_received(self, data):
        self._buffer = data.decode()
        # accumulation instead of assignment
        # self._buffer += data.decode()

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            print(f"Received line: {line!r}")
            self._handle_line(line)

    def _handle_line(self, line: str):
        try:
            request = json.loads(line)
            func_name = request.get("func_name")
            args = request.get("args", [])
            kwargs = request.get("kwargs", {})
            if func_name not in FUNCTIONS:
                response = {"error": f"unknown function {func_name!r}"}
            response = self._execute_function(func_name, *args, **kwargs)
        except Exception as e:
            response = {"error": f"bad request: {e!r}"}

        out = f"{json.dumps(response)}\n"
        print(f"Sending: {out!r}")
        self.transport.write(out.encode())
        self.transport.close()

    def _execute_function(self, func_name, *args, **kwargs):
        try:
            result = FUNCTIONS[func_name](*args, **kwargs)
            return {"result": result}
        except Exception as e:
            return {"error": repr(e)}


class EchoServerProtocal(asyncio.Protocol):
    def connection_made(self, transport):
        peername = transport.get_extra_info("peername")
        print(f"Connetion from {peername}")
        self.transport = transport

    def data_received(self, data):
        message = data.decode()
        print(f"Data recived: {message!r}")
        print(f"Send: {message!r}")
        self.transport.write(data)
        print("Close the client socket")
        self.transport.close()


async def main():
    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        RpcServerProtocol,
        "localhost",
        8080,
    )

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
