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


---

## R5 – Protocol Specification & Error Handling

All messages are **ASCII text lines** terminated by `\n` (newline).  
Unknown or malformed commands are handled with `ERROR ...` responses; servers do not crash.

### Message Types

#### Content Server → Index Server (TCP)
- **REGISTER**
```bash
REGISTER <server_id> <server_tcp_port> <server_udp_port>
```
Response:
```bash
OK REGISTERED
```

- **ADD_FILE / DONE_FILES**
```bash
ADD_FILE <server_id> <file_name> <file_size_bytes>
...
DONE_FILES
```
Response:
```bash
OK FILES_ADDED
```


#### Client → Index Server (TCP)
- **HELLO**
```bash
HELLO
```
Response(optional greeting,implemented):
```bash
WELCOME MICRO-CDN
```


- **GET (lookup)**
```bash
GET <file_name>
```
Success:
```bash
SERVER <ip> <tcp_port> <server_id> <file_size_bytes>
```
Failure:
```bash
ERROR FILE_NOT_FOUND
```

#### Client → Content Server (TCP)
- **GET (download)**
```bash
GET <file_name>
```
Success:
```bash
OK <file_size_bytes>
```
followed immediately by exactly `<file_size_bytes>` raw bytes on the same TCP connection.

Failure:
```bash
ERROR FILE_NOT_FOUND
```


#### Content Server → Monitor Server (UDP)
- **HEARTBEAT**
```bash
HEARTBEAT <server_id> <ip> <tcp_port> <load> <num_files>
```
Sent periodically (every ~3 seconds).  
`load` is the current active client count.

#### Index Server → Monitor Server (TCP)
- **LIST_SERVERS**
```bash
LIST_SERVERS
```
Response:
```bash
SERVER <server_id> <ip> <tcp_port> <load> <status>
...
END
```

#### Monitor Server → Index Server (TCP)
- **SERVER_DOWN**
```bash
SERVER_DOWN <server_id> <timestamp>
```
Sent immediately when the Monitor detects a heartbeat timeout for a server.

---

### Expected Sequences (State Machines)

#### 1) Content Server Startup Registration
1. Content Server connects to Index (TCP)
2. Sends `REGISTER ...`
3. Index replies `OK REGISTERED`
4. Content Server sends `ADD_FILE ...` for each file
5. Content Server sends `DONE_FILES`
6. Index replies `OK FILES_ADDED`
7. Content Server begins serving client downloads and sending UDP heartbeats

#### 2) Client Download Flow
1. Client connects to Index (TCP)
2. Sends `HELLO`
3. Sends `GET <file_name>`
4. Index replies `SERVER ...` or `ERROR FILE_NOT_FOUND`
5. If success: client connects to Content Server (TCP)
6. Client sends `GET <file_name>`
7. Content replies `OK <size>` then streams exactly `<size>` bytes
8. Client saves file locally and optionally verifies byte count

#### 3) Failure Detection Flow
1. Content Server stops sending heartbeats (crash/kill)
2. Monitor marks it dead after timeout (~8 seconds)
3. Monitor sends `SERVER_DOWN ...` to Index via TCP
4. Index marks server dead and stops routing new clients to it

---
## State Machines

This section describes the valid states and state transitions of each component in the Micro-CDN system.  
The state machines represent logical operating modes and are independent of any programming language or implementation details.

---

### Content Server State Machine

Each Content Server follows a clear lifecycle from startup to serving client requests.

#### States
- **INIT**  
  The Content Server process has started but has not yet contacted the Index Server.

- **REGISTERING**  
  The Content Server is connected to the Index Server over TCP and is executing the registration protocol by sending `REGISTER`, one or more `ADD_FILE` messages, and `DONE_FILES`.

- **ACTIVE**  
  The Content Server is fully operational:
  - It serves client file download requests over TCP.
  - It periodically sends UDP heartbeat messages to the Monitor Server.
  - It serves the files that were advertised during registration.

  In this implementation:
  - Content Server **CS1** serves files from the directory `content1_files`, which contains:
    - `file1` (empty file)
    - `file2` (empty file)
    - `hello` (text file containing a short message)
  - Content Server **CS2** serves files from the directory `content2_files`, which contains:
    - `file3` (empty file)
    - `file4` (empty file)

  Empty files are treated as valid files with size zero and are served normally by the protocol.

- **DEAD**  
  The Content Server process has terminated or crashed and no longer sends heartbeat messages.

#### Transitions
- **INIT → REGISTERING**  
  Triggered when the Content Server starts and opens a TCP connection to the Index Server.

- **REGISTERING → ACTIVE**  
  Triggered after receiving `OK REGISTERED` and `OK FILES_ADDED` from the Index Server.

- **ACTIVE → DEAD**  
  Triggered when the process terminates, crashes, or is manually killed, causing heartbeat messages to stop.

---

### Index Server State Machine

The Index Server maintains global system metadata and routes client requests.

#### States
- **INIT**  
  The Index Server has started and is initializing its internal data structures.

- **RUNNING**  
  The Index Server is actively accepting Content Server registrations, recording file advertisements, and handling client file lookup requests.

- **UPDATING**  
  The Index Server is processing a failure notification from the Monitor Server and updating the status of a Content Server.

#### Transitions
- **INIT → RUNNING**  
  Triggered when the Index Server successfully starts listening on its TCP port.

- **RUNNING → UPDATING**  
  Triggered upon receiving a `SERVER_DOWN <server_id>` message from the Monitor Server.

- **UPDATING → RUNNING**  
  Triggered after the specified Content Server is marked as dead and routing information is updated.

---

### Monitor Server State Machine

The Monitor Server detects Content Server failures using periodic heartbeats.

#### States
- **LISTENING**  
  The Monitor Server is receiving UDP heartbeat messages from Content Servers.

- **CHECKING**  
  The Monitor Server periodically checks the time elapsed since the last heartbeat of each Content Server.

- **REPORTING**  
  A Content Server heartbeat timeout has been detected and the failure is being reported to the Index Server.

#### Transitions
- **LISTENING → CHECKING**  
  Triggered periodically based on the configured heartbeat check interval.

- **CHECKING → REPORTING**  
  Triggered when a Content Server exceeds the heartbeat timeout threshold.

- **REPORTING → LISTENING**  
  Triggered after sending a `SERVER_DOWN` notification to the Index Server.

---

### Client State Machine

The Client follows a sequential workflow to locate and download a file.

#### States
- **IDLE**  
  The Client application has started and is ready to request a file.

- **QUERYING**  
  The Client is connected to the Index Server and is requesting the location of a file.

- **DOWNLOADING**  
  The Client is connected to a Content Server and is downloading the requested file.

- **DONE**  
  The file has been successfully downloaded and saved locally.

- **ERROR**  
  An error has occurred, such as file not found, invalid response, or connection failure.

#### Transitions
- **IDLE → QUERYING**  
  Triggered when the Client sends `HELLO` and `GET <file_name>` to the Index Server.

- **QUERYING → DOWNLOADING**  
  Triggered when the Index Server returns a valid `SERVER <ip> <port> <server_id> <file_size>` response.

- **QUERYING → ERROR**  
  Triggered when the Index Server returns `ERROR FILE_NOT_FOUND`.

- **DOWNLOADING → DONE**  
  Triggered after the Client receives exactly the expected number of bytes from the Content Server.

- **DOWNLOADING → ERROR**  
  Triggered if the TCP connection closes prematurely or an invalid response is received.

### Error Handling

#### Invalid / malformed commands
- Index / Content / Monitor respond with `ERROR ...` for unknown or malformed messages.
- Connections are closed cleanly after error response.

#### Unknown files
- Index returns:
```bash
ERROR FILE_NOT_FOUND
```
if the file is not present locally.

#### Client disconnects early
- Content Server catches socket errors and decreases load counter safely (no crash).

#### Content Server killed mid-run
- Monitor detects missing heartbeats and notifies Index.
- Index avoids routing clients to dead servers (routes to another alive server if available, otherwise returns `ERROR FILE_NOT_FOUND`).

---

