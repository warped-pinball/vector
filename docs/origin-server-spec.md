# Origin Server Specification

This document describes the HTTP and WebSocket interfaces required for the Origin server used by Vector machines.  The server will
be implemented with FastAPI and deployed in a Docker container.

## Overview

Vector devices call the Origin server to establish a shared secret and receive a claim link.  The server must expose a WebSocket
endpoint for the initial handshake and REST endpoints for claiming and status checks.

## WebSocket: `/ws/claim`

Establishes a shared secret between the device and Origin.

### Client → Server
- Connect to `ws://<origin-host>/ws/claim`.
- Send JSON payload: `{ "client_key": "<base64 x25519 public key>" }`.

### Server Behaviour
1. Generate an x25519 key pair.
2. Compute shared secret using the device key.
3. Create a unique `machine_id` (UUID) and a one-time `claim_code` (8–12 character alphanumeric).
4. Sign the shared secret with the RSA private key matching the public key baked into the device firmware.
5. Persist `{machine_id, claim_code, shared_secret, claimed=False}` in storage.

### Server → Client
Return JSON:
```json
{
  "server_key": "<base64 server public key>",
  "claim_code": "<claim code>",
  "machine_id": "<uuid>",
  "signature": "<hex RSA signature of shared_secret>"
}
```
Close the socket afterwards.

### Error Handling
- Malformed JSON → close connection.
- Internal errors → close connection and log; device should retry later.

## HTTP: `GET /claim`
Displays a web page that allows a user to claim a machine using the `claim_code`.

- Query parameter: `code` (required).
- Validate code; if invalid or already claimed return `404`.
- On success, render HTML with device information and a button to confirm claiming.

## HTTP: `POST /api/claim`
Programmatic endpoint for completing a claim.

- Request body: `{ "code": "<claim_code>", "user_id": "<user identifier>" }`.
- Validate code and associate `machine_id` with the user.
- Mark record as claimed and clear claim_code.
- Responses:
  - `204 No Content` on success
  - `404` if code not found
  - `409` if code already claimed

## HTTP: `GET /api/machines/{machine_id}/status`
Returns linking status for a machine so the device can poll.

- Response when claimed: `{ "linked": true }`
- Response when unclaimed or unknown: `{ "linked": false }`

## Security Considerations
- All HTTP endpoints served over HTTPS.
- The RSA key pair used for signing must be kept private; the public key is embedded in device firmware.
- Shared secrets are stored securely and will later be used to authenticate device communications (e.g., via HMAC headers).

## Docker Notes
- Base image: `python:3.11-slim`.
- Install dependencies: `fastapi`, `uvicorn[standard]`, `websockets`, `cryptography`.
- Expose port `80` and run `uvicorn` on startup.
