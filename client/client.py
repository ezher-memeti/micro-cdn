import socket
import argparse
import os


def recv_line(sock: socket.socket) -> str:
    """
    Read until '\n' and return the decoded line (without newline).
    This is safer than a single recv() because TCP can split packets.
    """
    data = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            # Connection closed before newline
            break
        if chunk == b"\n":
            break
        data.extend(chunk)
    return data.decode(errors="replace").strip("\r")


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """
    Read exactly n bytes from the socket (or raise if connection breaks).
    """
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(4096, n - len(buf)))
        if not chunk:
            raise ConnectionError("Connection closed before receiving expected bytes")
        buf.extend(chunk)
    return bytes(buf)


def request_from_index(index_host: str, index_port: int, filename: str):
    """
    Step 1 in assignment: connect to Index Server, send HELLO + GET <file>.
    Returns (ip, tcp_port, server_id, file_size) or raises ValueError.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((index_host, index_port))

        # HELLO
        s.sendall(b"HELLO\n")
        # Index may reply WELCOME MICRO-CDN (optional per assignment) :contentReference[oaicite:3]{index=3}
        # We'll read one line if available, but not require it.
        s.settimeout(1.0)
        try:
            _ = recv_line(s)
        except Exception:
            pass
        finally:
            s.settimeout(None)

        # GET <file>
        s.sendall(f"GET {filename}\n".encode())

        response = recv_line(s)
        if response.startswith("ERROR"):
            raise ValueError(response)

        # Expected: SERVER <ip> <tcp_port> <server_id> <file_size_bytes> :contentReference[oaicite:4]{index=4}
        parts = response.split()
        if len(parts) != 5 or parts[0] != "SERVER":
            raise ValueError(f"Unexpected Index response: {response}")

        ip = parts[1]
        tcp_port = int(parts[2])
        server_id = parts[3]
        file_size = int(parts[4])
        return ip, tcp_port, server_id, file_size


def download_from_content(content_ip: str, content_port: int, filename: str, out_path: str):
    """
    Step 2 in assignment: connect to Content Server and download the file via TCP.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((content_ip, content_port))
        s.sendall(f"GET {filename}\n".encode())

        header = recv_line(s)
        if header.startswith("ERROR"):
            raise ValueError(header)

        # Expected: OK <file_size_bytes> :contentReference[oaicite:5]{index=5}
        parts = header.split()
        if len(parts) != 2 or parts[0] != "OK":
            raise ValueError(f"Unexpected Content header: {header}")

        expected_size = int(parts[1])
        data = recv_exact(s, expected_size)

    # Save file
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)

    return expected_size


def parse_args():
    p = argparse.ArgumentParser(description="Micro-CDN Client")
    p.add_argument("filename", help="Name of file to download (e.g., hello.txt)")
    p.add_argument("--out", default=None, help="Output path (default: ./downloads/<filename>)")

    # Index mode (assignment standard)
    p.add_argument("--index-host", default="127.0.0.1")
    p.add_argument("--index-port", type=int, default=5000)

    # Direct mode (for testing before index is done)
    p.add_argument("--direct-host", default=None, help="Download directly from a content server host")
    p.add_argument("--direct-port", type=int, default=None, help="Download directly from a content server port")

    return p.parse_args()


def main():
    args = parse_args()
    out_path = args.out or os.path.join("downloads", args.filename)

    # If direct host/port are provided, skip index
    if args.direct_host and args.direct_port:
        print(f"[CLIENT] Direct download from {args.direct_host}:{args.direct_port}")
        size = download_from_content(args.direct_host, args.direct_port, args.filename, out_path)
        print(f"[CLIENT] Downloaded {args.filename} ({size} bytes) -> {out_path}")
        return

    # Otherwise use index (assignment flow)
    print(f"[CLIENT] Contacting Index at {args.index_host}:{args.index_port}")
    ip, port, server_id, idx_size = request_from_index(args.index_host, args.index_port, args.filename)
    print(f"[CLIENT] Index returned server {server_id} at {ip}:{port} (size={idx_size} bytes)")

    size = download_from_content(ip, port, args.filename, out_path)
    print(f"[CLIENT] Downloaded {args.filename} ({size} bytes) -> {out_path}")

    # Optional verification (assignment suggests it) :contentReference[oaicite:6]{index=6}
    if size != idx_size:
        print(f"[CLIENT][WARN] Size mismatch: index said {idx_size}, content sent {size}")


if __name__ == "__main__":
    main()

