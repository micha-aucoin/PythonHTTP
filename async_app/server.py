#!/usr/bin/env python

import asyncio
import inspect
import json
import logging
import time
from http import HTTPStatus
from pathlib import Path

# from pprint import pprint

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")


class HttpServerProtocol(asyncio.Protocol):
    def __init__(self):
        self.transport = None
        self.request = ""
        self.command = ""
        self.path = ""
        self.headers = {
            "Content-Type": "text/html",
            "Content-Length": "0",
            "Connection": "close",
        }

    def connection_made(self, transport):
        peername = transport.get_extra_info("peername")
        logging.info(f"Connetion from client socket {peername}")
        self.transport = transport

    def data_received(self, data):
        self._parse_request(data.decode())

        logging.info("Send to client socket")
        if not self._validate_path():
            self._404_not_found()
            logging.info("Closing the client socket")
            self.transport.close()
            return
        if self.command == "POST":
            self._403_forbidden()
            logging.info("Closing the client socket")
            self.transport.close()
            return
        if self.command not in ("GET", "HEAD"):
            self._405_method_not_allowed()
            logging.info("Closing the client socket")
            self.transport.close()
            return
        command = getattr(self, f"handle_{self.command}")
        command()

        logging.info("Closing the client socket")
        self.transport.close()

    def _parse_request(self, data: str):
        """Parse the request line and headers only"""
        # logging.info(f" -- Request: {request!r}")
        start_line, request = data.split("\r\n", 1)

        self.command = start_line.split(" ")[0]
        self.path = start_line.split(" ")[1]
        logging.info(f" -- COMMAND: {self.command!r}")
        logging.info(f" -- PATH: {self.path!r}")

        headers = {}
        while "\r\n\r\n" in request:
            header, request = request.split("\r\n", 1)
            headers[header.split(": ")[0]] = header.split(": ")[1]
        logging.info(f" -- HEADERS: {headers!r}")
        logging.info(f" -- Whats left of the request: {request!r}")

    def _validate_path(self) -> bool:
        """Validates the path. Returns True if the path is valid, False otherwise."""
        self.path = Path.cwd() / self.path.lstrip("/")

        if self.path.is_dir():
            self.path = self.path / "index.html"
        elif self.path.is_file():
            pass
        if not self.path.exists():
            return False
        return True

    def _404_not_found(self) -> None:
        """NOT FOUND"""
        self._write_response_line(404)
        self._write_headers()

    def _405_method_not_allowed(self) -> None:
        """METHOD NOT ALLOWED"""
        self._write_response_line(405)
        self._write_headers()

    def _403_forbidden(self) -> None:
        """FORBIDDEN"""
        self._write_response_line(403)
        self._write_headers()

    def handle_GET(self) -> None:
        """writes headers and the file to the socket"""
        self.handle_HEAD()
        with open(self.path, "rb") as f:
            body = f.read()
        self.transport.write(body)

    def handle_HEAD(self) -> None:
        """writes headers, Defualt 200 OK"""
        headers = {
            "Content-Length": self.path.stat().st_size,
        }
        self._write_response_line(200)
        self._write_headers(**headers)

    def _write_response_line(self, status_code: int) -> None:
        response_line = f"HTTP/1.1 {status_code} {HTTPStatus(status_code).phrase}\r\n"
        logging.info(f" -- {response_line!r}")
        self.transport.write(response_line.encode())

    def _write_headers(self, *args, **kwargs) -> None:
        headers_copy = self.headers.copy()
        headers_copy.update(**kwargs)
        header_lines = "\r\n".join(f"{k}: {v}" for k, v in headers_copy.items())
        logging.info(f" -- {headers_copy}")
        self.transport.write(header_lines.encode())
        self.transport.write(b"\r\n\r\n")


# ------------------------------------------------------------------------------


# class FunctionRegistry:
#     def __init__(self):
#         self.functions = {}
#
#     def register(self, name: str):
#         def decorator(fn):
#             self.functions[name] = fn
#             return fn
#
#         return decorator
#
#
# REGISTRY = FunctionRegistry()
#
#
# @REGISTRY.register("sleep")
# def sleep(t: int) -> None:
#     time.sleep(t)


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


@register("sleep")
def sleep(t: int) -> None:
    time.sleep(t)


class RpcServerProtocol(asyncio.Protocol):
    def __init__(self):
        self.transport = None
        self._buffer = ""

    def connection_made(self, transport):
        peername = transport.get_extra_info("peername")
        print(f"Connetion from {peername}")
        self.transport = transport

    def data_received(self, data):
        # self._buffer = data.decode()
        # accumulation instead of assignment
        self._buffer += data.decode()

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            print(f"Received line: {line!r}")
            asyncio.create_task(self._handle_line(line))

    async def _handle_line(self, line: str):
        try:
            request = json.loads(line)
            func_name = request.get("func_name")
            args = request.get("args", [])
            kwargs = request.get("kwargs", {})
            if func_name not in FUNCTIONS:
                response = {"error": f"unknown function {func_name!r}"}
            else:
                response = await self._execute_function(func_name, *args, **kwargs)
        except Exception as e:
            response = {"error": f"bad request: {e!r}"}

        out = f"{json.dumps(response)}\n"
        print(f"Sending: {out!r}")
        self.transport.write(out.encode())
        self.transport.close()

    async def _execute_function(self, func_name, *args, **kwargs):
        if inspect.iscoroutinefunction(FUNCTIONS[func_name]):
            try:
                result = await FUNCTIONS[func_name](*args, **kwargs)
                return {"result": result}
            except Exception as e:
                return {"error": repr(e)}
        try:
            result = await asyncio.to_thread(FUNCTIONS[func_name], *args, **kwargs)
            return {"result": result}
        except Exception as e:
            return {"error": repr(e)}


# ------------------------------------------------------------------------------


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
        # EchoServerProtocal,
        # RpcServerProtocol,
        HttpServerProtocol,
        "localhost",
        8080,
    )

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
