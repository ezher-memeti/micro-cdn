# Micro-CDN – CSE4074

## Requirements
Python 3.9+

## Components
- Index Server (TCP)
- Monitor Server (UDP + TCP)
- Content Servers (TCP + UDP)
- Client

## Ports
Index: 5000  
Monitor UDP: 6000  
Monitor TCP: 6001  
Content1: TCP 7001 / UDP 7002  
Content2: TCP 7101 / UDP 7102  

## How to Run
1. Start Monitor
2. Start Index
3. Start Content Servers
4. Run Client

## Protocol
(Describe REGISTER, ADD_FILE, GET, HEARTBEAT…)

## Test Scenario
(Describe killing a content server and observing behavior)
