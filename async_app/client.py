#!/usr/bin/env python

import asyncio
import json


class RpcClientProtocol(asyncio.Protocol):
    def __init__(
        self,
        request: dict,
        on_con_lost: asyncio.Future,
    ):
        self.request = request
        self.on_con_lost = on_con_lost
        self._buffer = ""

    def connection_made(self, transport):
        self.transport = transport
        msg = f"{json.dumps(self.request)}\n"
        print(f"Sending: {msg!r}")
        self.transport.write(msg.encode())

    def data_received(self, data):
        self._buffer += data.decode()
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            response = json.loads(line)
            print(f"Response from server: {response}")
            self.transport.close()

    def connection_lost(self, exc):
        print("The server closed the connetion")
        self.on_con_lost.set_result(True)


async def run_rpc_client(request: dict):
    loop = asyncio.get_running_loop()
    on_con_lost = loop.create_future()

    transport, protocol = await loop.create_connection(
        lambda: RpcClientProtocol(request, on_con_lost),
        "localhost",
        8080,
    )
    try:
        await on_con_lost
    finally:
        transport.close()


class EchoClientProtocol(asyncio.Protocol):
    def __init__(self, message, on_con_lost):
        self.message = message
        self.on_con_lost = on_con_lost

    def connection_made(self, transport):
        transport.write(self.message.encode())
        print(f"Data send: {self.message!r}")

    def data_received(self, data):
        print(f"Data received: {data.decode()!r}")

    def connection_lost(self, exc):
        print("The server closed the connection")
        self.on_con_lost.set_result(True)


async def run_echo_client(message: str):
    loop = asyncio.get_running_loop()
    on_con_lost = loop.create_future()

    transport, protocol = await loop.create_connection(
        lambda: EchoClientProtocol(message, on_con_lost),
        "localhost",
        8080,
    )
    try:
        await on_con_lost
    finally:
        transport.close()


async def main():
    await run_rpc_client({"func_name": "sleep", "args": [5]})
    await asyncio.gather(
        run_rpc_client({"func_name": "sleep", "args": [5]}),
        run_rpc_client({"func_name": "sleep", "args": [5]}),
        run_rpc_client({"func_name": "sleep", "args": [5]}),
    )
    await run_rpc_client({"func_name": "sleep", "args": [2]})
    await run_rpc_client({"func_name": "add", "args": [2, 3]}),
    await run_rpc_client({"func_name": "upper", "args": ["hello, world!"]})

    # await asyncio.gather(
    #     run_echo_client("hello 1"),
    #     run_echo_client("hello 2"),
    # )
    # await asyncio.gather(
    #     run_echo_client("hello 3"),
    #     run_echo_client("hello 4"),
    # )


if __name__ == "__main__":
    asyncio.run(main())
