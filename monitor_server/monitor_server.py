import socket
import threading
import time
import argparse


def recv_line(conn: socket.socket) -> str:
    data = bytearray()
    while True:
        b = conn.recv(1)
        if not b:
            break
        if b == b"\n":
            break
        data.extend(b)
    return data.decode(errors="replace").strip("\r")


def send_line(conn: socket.socket, line: str) -> None:
    conn.sendall((line + "\n").encode())


class MonitorState:
    def __init__(self, timeout_sec: float):
        self.timeout_sec = timeout_sec
        self.lock = threading.Lock()
        # server_id -> {ip, tcp_port, load, num_files, last_seen, status}
        self.servers = {}

    def update_heartbeat(self, server_id, ip, tcp_port, load, num_files):
        now = time.time()
        with self.lock:
            s = self.servers.get(server_id)
            if not s:
                self.servers[server_id] = {
                    "ip": ip,
                    "tcp_port": tcp_port,
                    "load": load,
                    "num_files": num_files,
                    "last_seen": now,
                    "status": "alive",
                }
                return "new_alive"
            else:
                was_dead = (s["status"] == "dead")
                s.update({
                    "ip": ip,
                    "tcp_port": tcp_port,
                    "load": load,
                    "num_files": num_files,
                    "last_seen": now,
                    "status": "alive",
                })
                return "revived" if was_dead else "alive"

    def mark_dead_and_get_list(self):
        """Mark servers dead if timed out. Return list of server_ids that newly became dead."""
        now = time.time()
        newly_dead = []
        with self.lock:
            for sid, s in self.servers.items():
                if s["status"] == "alive" and (now - s["last_seen"] > self.timeout_sec):
                    s["status"] = "dead"
                    newly_dead.append(sid)
        return newly_dead

    def snapshot_lines(self):
        with self.lock:
            lines = []
            for sid, s in sorted(self.servers.items()):
                lines.append(f"SERVER {sid} {s['ip']} {s['tcp_port']} {s['load']} {s['status']}")
            return lines


def notify_index_server_down(index_host: str, index_port: int, server_id: str):
    """
    Dedicated TCP notification message:
    SERVER_DOWN <server_id> <timestamp>
    (Assignment requires monitor to proactively inform index immediately.) :contentReference[oaicite:1]{index=1}
    """
    ts = int(time.time())
    msg = f"SERVER_DOWN {server_id} {ts}"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect((index_host, index_port))
            send_line(s, msg)
            # Optional: index may reply OK; we won't require it
    except Exception as e:
        print(f"[MONITOR] Failed to notify Index about {server_id} down: {e}")


def udp_listener(state: MonitorState, udp_port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", udp_port))
    print(f"[MONITOR] UDP listening on {udp_port}")

    while True:
        data, addr = sock.recvfrom(2048)
        line = data.decode(errors="replace").strip()
        # Expected: HEARTBEAT <server_id> <ip> <tcp_port> <load> <num_files> :contentReference[oaicite:2]{index=2}
        parts = line.split()
        if len(parts) != 6 or parts[0] != "HEARTBEAT":
            print(f"[MONITOR] Invalid heartbeat from {addr}: {line}")
            continue

        server_id = parts[1]
        ip = parts[2]
        tcp_port = int(parts[3])
        load = int(parts[4])
        num_files = int(parts[5])

        status = state.update_heartbeat(server_id, ip, tcp_port, load, num_files)
        if status in ("new_alive", "revived"):
            print(f"[MONITOR] {server_id} is ALIVE at {ip}:{tcp_port} (load={load}, files={num_files})")


def tcp_server(state: MonitorState, tcp_port: int):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", tcp_port))
    srv.listen(50)
    print(f"[MONITOR] TCP listening on {tcp_port}")

    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_tcp_client, args=(state, conn, addr), daemon=True)
        t.start()


def handle_tcp_client(state: MonitorState, conn: socket.socket, addr):
    try:
        line = recv_line(conn)
        if line != "LIST_SERVERS":
            send_line(conn, "ERROR UNKNOWN_COMMAND")
            return

        # Response lines:
        # SERVER <server_id> <ip> <tcp_port> <load> <status>
        # ...
        # END :contentReference[oaicite:3]{index=3}
        for l in state.snapshot_lines():
            send_line(conn, l)
        send_line(conn, "END")
    except Exception as e:
        print(f"[MONITOR] TCP client error {addr}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def dead_checker_loop(state: MonitorState, index_host: str, index_port: int, check_interval: float):
    while True:
        time.sleep(check_interval)
        newly_dead = state.mark_dead_and_get_list()
        for sid in newly_dead:
            print(f"[MONITOR] {sid} marked DEAD (heartbeat timeout)")
            # proactive notification to index
            notify_index_server_down(index_host, index_port, sid)


def parse_args():
    p = argparse.ArgumentParser(description="Monitor/Health Server")
    p.add_argument("--udp-port", type=int, default=6000)
    p.add_argument("--tcp-port", type=int, default=6001)
    p.add_argument("--timeout", type=float, default=8.0)         # suggested in PDF :contentReference[oaicite:4]{index=4}
    p.add_argument("--check-interval", type=float, default=1.0)

    # Where to notify index about failures:
    p.add_argument("--index-host", default="127.0.0.1")
    p.add_argument("--index-port", type=int, default=5050)       # your mac-friendly index port
    return p.parse_args()


def main():
    args = parse_args()
    state = MonitorState(timeout_sec=args.timeout)

    threading.Thread(target=udp_listener, args=(state, args.udp_port), daemon=True).start()
    threading.Thread(target=tcp_server, args=(state, args.tcp_port), daemon=True).start()
    threading.Thread(
        target=dead_checker_loop,
        args=(state, args.index_host, args.index_port, args.check_interval),
        daemon=True
    ).start()

    # Keep main alive
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
