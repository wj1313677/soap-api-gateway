# 🛰 Hybrid SOAP→REST Gateway (Async + Cache + MCP + FastAPI)

A production‑grade gateway that:

- Converts **SOAP WSDL services** into a **REST‑style interface**.
- Runs **FastAPI HTTP API** and **MCP server** as **separate processes** in the same container via `supervisord`.
- Supports **WS‑Security UsernameToken** authentication from `.env`.
- Caches **raw WSDL XML** and **fully processed WSDL** (Zeep client, docs, examples).
- Allows **manual cache clear** and **manual processed WSDL refresh** via HTTP or MCP.
- Uses `.env` for environment‑specific configuration.

---

## 📂 Project Structure

```
.
├── soap_gateway.py      # Shared SOAP→REST logic
├── fastapi_app.py       # FastAPI HTTP API
├── mcp_server.py        # MCP server
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container build instructions
├── docker-compose.yml   # docker compose file
├── .env                 # Environment variables
└── README.md            # This file
```

---

## 🚀 Features

- **Dual‑process**: FastAPI and MCP run independently — no blocking.
- **Async‑ready**: Core functions can be adapted for async.
- **Caching**:
  - Raw WSDL XML
  - Fully processed WSDL (Zeep client, operation docs, element docs)
- **Clear cache**: `/clear_cache` endpoint or MCP `clear()` tool.
- **Refresh processed WSDL**: `/refresh_wsdl` endpoint or MCP `refresh_wsdl()` tool.
- **Dockerized**: Minimal image with `supervisord` managing both processes.
- **Configurable health check**: WSDL URL set via `HEALTHCHECK_WSDL_URL` env var.

---

## ⚙️ Environment Variables

| Variable                | Purpose                                                                                 | Default                          |
|-------------------------|-----------------------------------------------------------------------------------------|-----------------------------------|
| `HEALTHCHECK_WSDL_URL`  | WSDL URL used by health check and as default for `/describe` and MCP `describe`         | `http://example.com?wsdl`        |
| `SOAP_USERNAME`         | Username for WS‑Security UsernameToken authentication                                  | *(none)*                         |
| `SOAP_PASSWORD`         | Password for WS‑Security UsernameToken authentication                                  | *(none)*                         |
| `DEBUG`                 | If `true`, returns full error + traceback in responses                                 | `false`                          |
| `PORT`                  | Port for FastAPI HTTP server                                                            | `9000`                           |

---

### 📄 Example `.env`

```env
HEALTHCHECK_WSDL_URL=https://dev.example.com/service?wsdl
SOAP_USERNAME=myuser
SOAP_PASSWORD=supersecret
DEBUG=true
PORT=9000
```
---

## 🐳 Docker Deployment

```bash
docker compose up -d
```
---

## 🛠 Usage

### 1. HTTP API (FastAPI)

- http://localhost:9000/docs - FastAPI documentation
- `POST /describe` — List operations and input schema.
- `POST /invoke` — Call a SOAP operation.
- `POST /clear_cache` — Flush all caches.
- `POST /refresh_wsdl` — Force rebuild of processed WSDL cache.

---

### 2. MCP Server

Tools:
- `describe(wsdl_url=None, operation=None, username=None, password=None)`
- `invoke(wsdl_url=None, endpoint_url, operation, params, username=None, password=None)`
- `clear()`
- `refresh_wsdl(wsdl_url=None, username=None, password=None, version="v1")`

HTTP MCP transport (mounted at `/mcp`)

The MCP wrapper in `mcp_server.py` mounts an HTTP transport at `/mcp` by default.
When calling the HTTP MCP endpoint, send a JSON POST where `tool` is the tool
name and `args` is an object containing the tool arguments. Example payload:

```json
{
  "tool": "describe",
  "args": {
    "wsdl_url": "https://example.com/service?wsdl",
    "operation": null,
    "username": null,
    "password": null
  }
}
```

The endpoint will return a JSON response containing the tool result (same
shape as the internal function return values). This is useful for MCP agents
that communicate over HTTP instead of stdio.

---

## 🤝 MCP Agent Configuration

### Local spawn (stdio)
```jsonc
{
  "mcpServers": {
    "soap-gateway": {
      "type": "stdio",
      "command": "python",
      "args": ["mcp_server.py"],
      "env": {
        "HEALTHCHECK_WSDL_URL": "https://dev.example.com/service?wsdl",
        "SOAP_USERNAME": "myuser",
        "SOAP_PASSWORD": "supersecret"
      }
    }
  }
}
```

### Remote/HTTP
```jsonc
{
  "mcpServers": {
    "soap-gateway": {
      "type": "http",
      "url": "http://your-server-host:9010/mcp",
      "env": {
        "HEALTHCHECK_WSDL_URL": "https://prod.example.com/service?wsdl",
        "SOAP_USERNAME": "myuser",
        "SOAP_PASSWORD": "supersecret"
      }
    }
  }
}
```

---

## 🐳 MCP Configuration for Docker Deployment

When running inside Docker, connect over HTTP:

```jsonc
{
  "mcpServers": {
    "soap-gateway": {
      "type": "http",
      "url": "http://localhost:9010/mcp",
      "env": {
        "HEALTHCHECK_WSDL_URL": "https://dev.example.com/service?wsdl",
        "SOAP_USERNAME": "myuser",
        "SOAP_PASSWORD": "supersecret"
      }
    }
  }
}
```
---

## ❤️ Health Check

```dockerfile
ENV HEALTHCHECK_WSDL_URL="http://example.com?wsdl"
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -sf http://localhost:9000/describe \
       -H "Content-Type: application/json" \
       -d "{\"wsdl_url\":\"${HEALTHCHECK_WSDL_URL}\"}" || exit 1
```

---

## 🧹 Cache Management

- **Automatic**: Processed WSDL cache is built on first use and reused until cleared or refreshed.
- **Manual clear**:
  - HTTP: `POST /clear_cache`
  - MCP: `clear()` tool
- **Manual refresh**:
  - HTTP: `POST /refresh_wsdl`
  - MCP: `refresh_wsdl()` tool
