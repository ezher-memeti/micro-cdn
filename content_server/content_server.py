import socket
import threading
import os
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Content Server")
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--tcp-port", type=int, required=True)
    parser.add_argument("--files", required=True, help="Directory with files")
    return parser.parse_args()

active_clients = 0
active_clients_lock = threading.Lock()

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
