import socket
import threading
import os
import argparse
import time

def parse_args():
    parser = argparse.ArgumentParser(description="Content Server")
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--tcp-port", type=int, required=True)
    parser.add_argument("--udp-port", type=int, required=True)  # NEW (for REGISTER + later heartbeats)
    parser.add_argument("--files", required=True, help="Directory with files")

    # index connection info
    parser.add_argument("--index-host", default="127.0.0.1")
    parser.add_argument("--index-port", type=int, default=5050)  # macOS-friendly default

    parser.add_argument("--monitor-host", default="127.0.0.1")
    parser.add_argument("--monitor-udp-port", type=int, default=6000)


    return parser.parse_args()


active_clients = 0
active_clients_lock = threading.Lock()

def heartbeat_loop(server_id: str, tcp_port: int, files_dir: str,
                   monitor_host: str, monitor_udp_port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # For localhost testing, tell monitor ip=127.0.0.1
    ip = "127.0.0.1"

    while True:
        try:
            num_files = sum(
                1 for name in os.listdir(files_dir)
                if os.path.isfile(os.path.join(files_dir, name))
            )
            with active_clients_lock:
                load = active_clients

            msg = f"HEARTBEAT {server_id} {ip} {tcp_port} {load} {num_files}"
            sock.sendto(msg.encode(), (monitor_host, monitor_udp_port))
        except Exception as e:
            print(f"[CONTENT {server_id}] Heartbeat error: {e}")

        time.sleep(3)  # suggested interval :contentReference[oaicite:8]{index=8}


def register_with_index(server_id: str, tcp_port: int, udp_port: int, files_dir: str,
                        index_host: str, index_port: int):
    """
    Implements assignment protocol:
    REGISTER ... then ADD_FILE ... then DONE_FILES
    """
    # Build file list
    entries = []
    for name in os.listdir(files_dir):
        path = os.path.join(files_dir, name)
        if os.path.isfile(path):
            entries.append((name, os.path.getsize(path)))

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((index_host, index_port))

        # REGISTER <server_id> <server_tcp_port> <server_udp_port>
        send_line(s, f"REGISTER {server_id} {tcp_port} {udp_port}")
        resp = recv_line(s)
        if resp != "OK REGISTERED":
            raise RuntimeError(f"Index REGISTER failed: {resp}")

        # ADD_FILE <server_id> <file_name> <file_size_bytes>
        for fname, fsize in entries:
            send_line(s, f"ADD_FILE {server_id} {fname} {fsize}")

        send_line(s, "DONE_FILES")
        resp2 = recv_line(s)
        if resp2 != "OK FILES_ADDED":
            raise RuntimeError(f"Index FILES_ADDED failed: {resp2}")

    return len(entries)


def recv_line(sock: socket.socket) -> str:
    data = bytearray()
    while True:
        b = sock.recv(1)
        if not b:
            break
        if b == b"\n":
            break
        data.extend(b)
    return data.decode(errors="replace").strip("\r")


def send_line(sock: socket.socket, line: str) -> None:
    sock.sendall((line + "\n").encode())


def handle_client(conn, addr, files_dir):
    global active_clients

    with active_clients_lock:
        active_clients += 1

    print(f"[CONTENT] Client connected from {addr}. Load={active_clients}")

    try:
        request = conn.recv(1024).decode().strip()
        print(f"[CONTENT] Received: {request}")

        if not request.startswith("GET "):
            conn.sendall(b"ERROR INVALID_COMMAND\n")
            return

        filename = request.split(" ", 1)[1]
        filepath = os.path.join(files_dir, filename)

        if not os.path.isfile(filepath):
            conn.sendall(b"ERROR FILE_NOT_FOUND\n")
            return

        filesize = os.path.getsize(filepath)
        conn.sendall(f"OK {filesize}\n".encode())

        with open(filepath, "rb") as f:
            while True:
                data = f.read(4096)
                if not data:
                    break
                conn.sendall(data)

        print(f"[CONTENT] Sent file '{filename}' ({filesize} bytes)")

    except Exception as e:
        print(f"[CONTENT] Error: {e}")

    finally:
        conn.close()
        with active_clients_lock:
            active_clients -= 1
        print(f"[CONTENT] Client disconnected. Load={active_clients}")


def main():
    args = parse_args()

    print(f"[CONTENT {args.server_id}] Registering with Index at {args.index_host}:{args.index_port} ...")
    num_files = register_with_index(
        server_id=args.server_id,
        tcp_port=args.tcp_port,
        udp_port=args.udp_port,
        files_dir=args.files,
        index_host=args.index_host,
        index_port=args.index_port
    )
    print(f"[CONTENT {args.server_id}] Registered OK. Advertised {num_files} files.")

    threading.Thread(
    target=heartbeat_loop,
    args=(args.server_id, args.tcp_port, args.files, args.monitor_host, args.monitor_udp_port),
    daemon=True
    ).start()
    print(f"[CONTENT {args.server_id}] Heartbeats -> {args.monitor_host}:{args.monitor_udp_port}")



    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", args.tcp_port))
    server_socket.listen(5)

    print(f"[CONTENT {args.server_id}] Listening on TCP port {args.tcp_port}")
    print(f"[CONTENT {args.server_id}] Serving files from {args.files}")

    while True:
        conn, addr = server_socket.accept()
        thread = threading.Thread(
            target=handle_client,
            args=(conn, addr, args.files),
            daemon=True
        )
        thread.start()

if __name__ == "__main__":
    main()
