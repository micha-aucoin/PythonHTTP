from __future__ import annotations

import io
import logging
import os
import socket
from http import HTTPStatus

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")


# BASIC TCP SOCKET SERVER
# ----------------------------------------------------
# with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
#     sock.bind((HOST, PORT))
#     sock.listen()
#     print(f"listening on {HOST}:{PORT}")
#     conn, addr = sock.accept()
#     with conn:
#         print(f"Connected to {addr}")
#         while True:
#             data = conn.recv(1024)
#             print(f"Received {data}")
#             if not data:
#                 break
#             conn.sendall(data)
# ----------------------------------------------------


class TestHTTPHandler:
    """
    serves static files as-is. Only supports GET and HEAD.
    POST returns 403 FORBIDDEN. Other commands return 405 METHOD NOT ALLOWED.

    Supports HTTP/1.1
    """

    def __init__(
        self,
        request_stream: io.BufferedIOBse,
        response_stream: io.BufferedIOBse,
    ):
        self.request_stream = request_stream
        self.response_stream = response_stream
        self.command = ""
        self.path = ""
        self.data = ""
        self.headers = {
            "Content-Type": "text/html",
            "Content-Lenght": "0",
            "Connection": "close",
        }
        self.handle()

    def handle(self) -> None:
        """
        Handles the requests:

        Anthing but GET or HEAD will return 405
        POST will return 403

        self._parses_requests will populates
            self.commnad
            self.path
            self.headers
        """
        self._parse_request()

        if not self._validate_path():
            return self._404_not_found()
        if self.command == "POST":
            return self._403_forbidden()
        if self.command not in ("GET", "HEAD"):
            return self._405_method_not_allowed()

        command = getattr(self, f"handle_{self.command}")
        command()

    def _validate_path(self) -> bool:
        """
        Validates the path. Returns True if the path is valid, False otherwise.
        The path can either be a file or a directory
            If it's a directory, look for the index.html
            If it's a file, serve it
        """
        self.path = os.path.join(os.getcwd(), self.path.lstrip("/"))

        if os.path.isdir(self.path):
            self.path = os.path.join(self.path, "index.html")
        elif os.path.isfile(self.path):
            pass
        if not os.path.exists(self.path):
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

    def _parse_request(self):
        """
        Parse the request line
        Parse the headers
        """
        requestline = self.request_stream.readline().decode()
        requestline = requestline.rstrip("\r\n")
        logging.info(f"Parsing request line: {requestline}")
        self.command = requestline.split(" ")[0]
        self.path = requestline.split(" ")[1]

        headers = {}
        line = self.request_stream.readline().decode()
        while line not in ("\r\n", "\n", "\r", ""):
            logging.info(f"Parsing header: {line.rstrip("\r\n")}")
            header = line.rstrip("\r\n").split(": ")
            headers[header[0]] = header[1]
            line = self.request_stream.readline().decode()
        logging.info(f"Parsed headers: {headers}")

    def handle_GET(self) -> None:
        """
        Writes headers and the file to the socket.
        """
        self.handle_HEAD()
        with open(self.path, "rb") as f:
            body = f.read()
        self.response_stream.write(body)
        self.response_stream.flush()

    def handle_HEAD(self) -> None:
        """
        Writes headers to the socket.

        Default to 200 OK
        """
        headers = {
            "Content-Length": os.path.getsize(self.path),
        }
        self._write_response_line(200)
        self._write_headers(**headers)
        self.response_stream.flush()

    def _write_response_line(self, status_code: int) -> None:
        response_line = f"HTTP/1.1 {status_code} {HTTPStatus(status_code).phrase}"
        logging.info(response_line)
        self.response_stream.write(response_line.encode())

    def _write_headers(self, *args, **kwargs) -> None:
        headers_copy = self.headers.copy()
        headers_copy.update(**kwargs)
        header_lines = "\r\n".join(f"{k}: {v}" for k, v in headers_copy.items())
        logging.info(header_lines.replace("\r\n", " "))
        self.response_stream.write(header_lines.encode())
        self.response_stream.write(b"\r\n\r\n")


class TestTCPServer:
    def __init__(
        self,
        socket_address: tuple[str, int],
        request_handler: TestHTTPHandler,
    ) -> None:
        self.request_handler = request_handler

        # create a TCP socket using the IPv4 address family
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # allow re-binding on the same socket address after connction closes
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # bind and listen to socket
        self.sock.bind(socket_address)
        self.sock.listen()
        logging.info(f"listening on {socket_address[0]}:{socket_address[1]}")

    def serve_forever(self) -> None:
        while True:
            conn, addr = self.sock.accept()

            with conn:
                logging.info(f"Accepted connection from {addr}")

                # create a file-like object to read/write bytes sent
                #   from the client socket as if we're reading from a file.
                request_stream = conn.makefile("rb")
                response_stream = conn.makefile("wb")
                # `<this is similar to socket.recv()/socket.send()>

                self.request_handler(
                    request_stream=request_stream,
                    response_stream=response_stream,
                )

            logging.info(f"Closed connection from {addr}")

    def __enter__(self) -> TestTCPServer:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8080
    with TestTCPServer(
        socket_address=(HOST, PORT),
        request_handler=TestHTTPHandler,
    ) as server:
        server.serve_forever()
