# Micro-CDN – CSE4074

## Overview
This project implements a simplified **Content Delivery Network (Micro-CDN)** using TCP and UDP sockets.  
The system includes an **Index Server**, multiple **Content Servers**, a **Monitor/Health Server**, and a **Client**.

It demonstrates:
- TCP & UDP communication
- Concurrent server design
- Custom text-based protocols
- Failure detection via heartbeats

---

## Components
- **Index Server (TCP):** Tracks files and routes clients to content servers.
- **Content Servers (TCP + UDP):** Store files, serve clients, send heartbeats.
- **Monitor Server (UDP + TCP):** Detects failed content servers and notifies Index.
- **Client:** Requests files and downloads them.

---

## Protocols Used
- Client ↔ Index: TCP  
- Client ↔ Content: TCP  
- Content ↔ Index (registration): TCP  
- Content → Monitor (heartbeats): UDP  
- Monitor → Index (failure notification): TCP  

---

## Ports
> macOS reserves port 5000, so Index runs on **5050**.

| Component | Port |
|---------|------|
| Index Server | TCP 5050 |
| Monitor Server | UDP 6000 / TCP 6001 |
| Content Server 1 | TCP 7001 / UDP 7002 |
| Content Server 2 | TCP 7101 / UDP 7102 |

---

## How to Run

### Start Index
```bash
python index_server/index_server.py --port 5050
```
### Start Monitor
```bash
python monitor_server/monitor_server.py --index-port 5050
```

### Start Content Servers
```bash
python content_server/content_server.py \
  --server-id CS1 --tcp-port 7001 --udp-port 7002 \
  --files content_server/content1_files \
  --index-port 5050 --monitor-udp-port 6000
```
```bash
python content_server/content_server.py \
  --server-id CS2 --tcp-port 7101 --udp-port 7102 \
  --files content_server/content2_files \
  --index-port 5050 --monitor-udp-port 6000

```
### Run Client
```bash
python client/client.py hello.txt --index-port 5050
```

### Test Scenario
1. Start Monitor and Index servers

2. Start two Content Servers

3. Run multiple clients requesting files

4. Observe heartbeats in Monitor

5. Kill a Content Server

6. Monitor marks it dead and Index avoids routing to it