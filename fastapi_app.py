import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from soap_gateway import describe_operations, invoke_operation, clear_cache, get_processed_wsdl
import traceback

load_dotenv()
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"
DEFAULT_WSDL_URL = os.getenv("HEALTHCHECK_WSDL_URL", "http://example.com?wsdl")

app = FastAPI(title="SOAP→REST Gateway")

class DescribeRequest(BaseModel):
    wsdl_url: str = None
    operation: str = None
    username: str = None
    password: str = None

class InvokeRequest(BaseModel):
    wsdl_url: str = None
    endpoint_url: str
    operation: str
    params: dict
    username: str = None
    password: str = None

class RefreshRequest(BaseModel):
    wsdl_url: str = None
    username: str = None
    password: str = None
    version: str = "v1"

@app.post("/describe")
async def describe_endpoint(req: DescribeRequest):
    try:
        return describe_operations(req.wsdl_url, req.operation, req.username, req.password)
    except Exception as e:
        if DEBUG_MODE:
            return {"error": str(e), "traceback": traceback.format_exc()}
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/invoke")
async def invoke_endpoint(req: InvokeRequest):
    try:
        return {"data": invoke_operation(req.wsdl_url, req.endpoint_url, req.operation, req.params, req.username, req.password)}
    except Exception as e:
        if DEBUG_MODE:
            return {"error": str(e), "traceback": traceback.format_exc()}
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/clear_cache")
async def clear_cache_endpoint():
    try:
        clear_cache()
        return {"status": "ok", "message": "All caches cleared"}
    except Exception as e:
        if DEBUG_MODE:
            return {"error": str(e), "traceback": traceback.format_exc()}
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/refresh_wsdl")
async def refresh_wsdl_endpoint(req: RefreshRequest):
    try:
        wsdl_url = req.wsdl_url or DEFAULT_WSDL_URL
        get_processed_wsdl(wsdl_url, req.username, req.password, version=req.version, force_refresh=True)
        return {"status": "ok", "message": f"Processed WSDL cache refreshed for {wsdl_url} (version={req.version})"}
    except Exception as e:
        if DEBUG_MODE:
            return {"error": str(e), "traceback": traceback.format_exc()}
        raise HTTPException(status_code=500, detail="Internal Server Error")
