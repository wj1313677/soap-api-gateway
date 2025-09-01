# mcp_server.py
from fastapi_mcp import FastApiMCP
from fastapi_app import app as gateway_app  # import your existing FastAPI app

# Wrap the existing app with MCP
mcp = FastApiMCP(
    gateway_app,
    name="SOAP→REST MCP Gateway",
    describe_all_responses=True,
    describe_full_response_schema=True
)

# Mount HTTP transport for MCP
mcp.mount_http()

# Expose wrapped app for uvicorn
app = gateway_app
