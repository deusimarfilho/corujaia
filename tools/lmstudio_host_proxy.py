import os
import selectors
import socket
import threading


LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.environ.get("LMSTUDIO_PROXY_PORT", "1235"))
TARGET_PORT = int(os.environ.get("LMSTUDIO_TARGET_PORT", "1234"))


def detect_windows_gateway() -> str:
    with open("/proc/net/route", "r", encoding="utf-8") as route_file:
        next(route_file)
        for line in route_file:
            fields = line.strip().split()
            if len(fields) < 3:
                continue
            destination = fields[1]
            gateway_hex = fields[2]
            if destination != "00000000":
                continue
            gateway_bytes = bytes.fromhex(gateway_hex)
            gateway_bytes = gateway_bytes[::-1]
            return ".".join(str(part) for part in gateway_bytes)
    raise RuntimeError("Could not detect Windows host gateway from /proc/net/route")


TARGET_HOST = detect_windows_gateway()


def pipe_bidirectional(client: socket.socket, upstream: socket.socket) -> None:
    selector = selectors.DefaultSelector()
    selector.register(client, selectors.EVENT_READ, upstream)
    selector.register(upstream, selectors.EVENT_READ, client)
    sockets = (client, upstream)

    try:
      while True:
            events = selector.select()
            if not events:
                continue
            for key, _ in events:
                source = key.fileobj
                target = key.data
                data = source.recv(65536)
                if not data:
                    return
                target.sendall(data)
    finally:
        selector.close()
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()


def handle_client(client: socket.socket, client_addr) -> None:
    try:
        upstream = socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=10)
    except OSError as exc:
        print(f"[lmstudio-proxy] connect failed for {client_addr}: {exc}", flush=True)
        client.close()
        return

    print(
        f"[lmstudio-proxy] proxying {client_addr[0]}:{client_addr[1]} -> {TARGET_HOST}:{TARGET_PORT}",
        flush=True,
    )
    pipe_bidirectional(client, upstream)


def serve() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen()
    print(
        f"[lmstudio-proxy] listening on {LISTEN_HOST}:{LISTEN_PORT} and forwarding to {TARGET_HOST}:{TARGET_PORT}",
        flush=True,
    )

    try:
        while True:
            client, addr = server.accept()
            thread = threading.Thread(target=handle_client, args=(client, addr), daemon=True)
            thread.start()
    finally:
        server.close()


if __name__ == "__main__":
    serve()
