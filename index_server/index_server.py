import socket
import threading
import argparse
import time


# ---------------------------
# Shared socket helpers
# ---------------------------

def recv_line(conn: socket.socket) -> str:
    """Read a single ASCII line ending in '\n'. Returns '' if connection closes."""
    data = bytearray()
    while True:
        chunk = conn.recv(1)
        if not chunk:
            break
        if chunk == b"\n":
            break
        data.extend(chunk)
    return data.decode(errors="replace").strip("\r")


def send_line(conn: socket.socket, line: str) -> None:
    conn.sendall((line + "\n").encode())


# ---------------------------
# Index server state
# ---------------------------

class IndexState:
    """
    Stores:
    - servers: server_id -> {ip, tcp_port, udp_port, load, status, last_update}
    - files: file_name -> { server_id -> file_size }
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.servers = {}
        self.files = {}

    def register_server(self, server_id: str, ip: str, tcp_port: int, udp_port: int):
        with self.lock:
            self.servers[server_id] = {
                "ip": ip,
                "tcp_port": tcp_port,
                "udp_port": udp_port,
                "load": 0,
                "status": "alive",
                "last_update": time.time(),
            }

    def add_file(self, server_id: str, file_name: str, file_size: int):
        with self.lock:
            if file_name not in self.files:
                self.files[file_name] = {}
            self.files[file_name][server_id] = file_size

    def choose_server_for_file(self, file_name: str):
        """
        Return (ip, tcp_port, server_id, file_size) with lowest load among alive servers.
        """
        with self.lock:
            if file_name not in self.files:
                return None

            candidates = []
            for server_id, file_size in self.files[file_name].items():
                s = self.servers.get(server_id)
                if not s:
                    continue
                if s["status"] != "alive":
                    continue
                candidates.append((s["load"], s["ip"], s["tcp_port"], server_id, file_size))

            if not candidates:
                return None

            candidates.sort(key=lambda x: x[0])  # lowest load first
            _, ip, tcp_port, server_id, file_size = candidates[0]
            return ip, tcp_port, server_id, file_size


# ---------------------------
# Connection handler
# ---------------------------

def handle_connection(conn: socket.socket, addr, state: IndexState):
    """
    Handles both content servers and clients.
    We detect which one it is by the first command line:
    - REGISTER ... -> content server flow
    - HELLO -> client flow
    """
    ip = addr[0]
    try:
        first = recv_line(conn)
        if not first:
            return

        # -------- Content server flow --------
        if first.startswith("REGISTER "):
            parts = first.split()
            if len(parts) != 4:
                send_line(conn, "ERROR INVALID_REGISTER")
                return

            server_id = parts[1]
            server_tcp_port = int(parts[2])
            server_udp_port = int(parts[3])

            state.register_server(server_id, ip, server_tcp_port, server_udp_port)
            send_line(conn, "OK REGISTERED")
            print(f"[INDEX] Registered {server_id} at {ip}:{server_tcp_port}")

            # Receive file list
            while True:
                line = recv_line(conn)
                if not line:
                    return

                if line == "DONE_FILES":
                    break

                if not line.startswith("ADD_FILE "):
                    send_line(conn, "ERROR INVALID_FILE_ENTRY")
                    return

                fparts = line.split()
                # ADD_FILE <server_id> <file_name> <file_size_bytes>
                if len(fparts) != 4:
                    send_line(conn, "ERROR INVALID_FILE_ENTRY")
                    return

                sid = fparts[1]
                fname = fparts[2]
                fsize = int(fparts[3])

                state.add_file(sid, fname, fsize)

            send_line(conn, "OK FILES_ADDED")
            print(f"[INDEX] File list received from {server_id}")
            return

        # -------- Client flow --------
        if first == "HELLO":
            # Optional greeting in spec
            send_line(conn, "WELCOME MICRO-CDN")

            line = recv_line(conn)
            if not line:
                return

            if not line.startswith("GET "):
                send_line(conn, "ERROR INVALID_COMMAND")
                return

            file_name = line.split(" ", 1)[1]
            chosen = state.choose_server_for_file(file_name)
            if not chosen:
                send_line(conn, "ERROR FILE_NOT_FOUND")
                print(f"[INDEX] Client asked for '{file_name}' -> not found")
                return

            cip, cport, server_id, fsize = chosen
            send_line(conn, f"SERVER {cip} {cport} {server_id} {fsize}")
            print(f"[INDEX] Routed '{file_name}' -> {server_id} ({cip}:{cport})")
            return

        # Unknown first command
        send_line(conn, "ERROR UNKNOWN_FIRST_COMMAND")

    except Exception as e:
        print(f"[INDEX] Error with {addr}: {e}")

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------
# Main server loop
# ---------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Index Server")
    p.add_argument("--port", type=int, default=5000)
    return p.parse_args()


def main():
    args = parse_args()
    state = IndexState()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", args.port))
    server_socket.listen(50)

    print(f"[INDEX] Listening on TCP port {args.port}")

    while True:
        conn, addr = server_socket.accept()
        t = threading.Thread(target=handle_connection, args=(conn, addr, state), daemon=True)
        t.start()


if __name__ == "__main__":
    main()
