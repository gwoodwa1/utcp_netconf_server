# app.py
import os
import logging
from typing import Optional, Type, Dict, Any

from fastapi import FastAPI, Body, Query
from pydantic import BaseModel, Field
from scrapli_netconf.driver.async_driver import AsyncNetconfDriver

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("netconf_tools")

logging.getLogger("scrapli").setLevel(logging.DEBUG)
logging.getLogger("scrapli_asyncssh.transport").setLevel(logging.DEBUG)

app = FastAPI(
    title="NETCONF Tools",
    version="1.0.0",
    description="HTTP wrappers around scrapli_netconf for UTCP tool calls.",
)

# --------- Models ---------
class BaseConn(BaseModel):
    host: str = Field(..., description="NETCONF host/IP")
    port: int = Field(830, description="NETCONF port")
    timeout_ops: int = Field(120, description="Operation timeout (s)")
    username: Optional[str] = Field(default=None, description="Override env NETCONF_USER")
    password: Optional[str] = Field(default=None, description="Override env NETCONF_PASS")

class GetConfigRequest(BaseConn):
    source: str = Field("running", pattern="^(running|candidate)$")
    filter_xml: Optional[str] = Field(default=None, description="Subtree filter XML")

class EditConfigRequest(BaseConn):
    target: str = Field("running", pattern="^(running|candidate)$")  # Arista: typically running
    config_xml: str = Field(..., description="Full <config>...</config> XML")
    default_operation: str = Field("merge", pattern="^(merge|replace|none)$")
    test_option: str = Field("set", pattern="^(test-then-set|set)$")
    error_option: str = Field("stop-on-error", pattern="^(stop-on-error|continue-on-error)$")

class CommitRequest(BaseConn):
    confirmed: bool = False
    confirm_timeout: int = 120
    comment: Optional[str] = None

class RpcRequest(BaseConn):
    rpc_xml: str = Field(..., description="Raw RPC XML body")

# --------- Helpers ---------
def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    return v if v is not None and v != "" else default

def _mask(v: Optional[str]) -> str:
    if not v:
        return "<empty>"
    if len(v) <= 4:
        return "*" * len(v)
    return v[:2] + "*" * (len(v) - 4) + v[-2:]

def _device(req: BaseConn) -> Dict[str, Any]:
    user = req.username or _env("NETCONF_USER", "lab")
    pwd = req.password or _env("NETCONF_PASS", "")
    log.info(
        "NETCONF connect host=%s port=%s user=%s pass=%s timeout_ops=%s",
        req.host, req.port, user, _mask(pwd), req.timeout_ops
    )
    return {
        "host": req.host,
        "port": req.port,
        "auth_username": user,
        "auth_password": pwd,
        "auth_strict_key": False,
        "transport": "asyncssh",
        "timeout_ops": req.timeout_ops,
    }

def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _merge_to_model(model_cls: Type[BaseModel], body: Optional[BaseModel], **overrides) -> BaseModel:
    """Allow JSON body or query params; query params override body."""
    data: Dict[str, Any] = body.dict() if body is not None else {}
    for k, v in overrides.items():
        if v is not None:
            data[k] = v
    return model_cls(**data)
  
# --------- Endpoints ---------
@app.post("/netconf/get-config", operation_id="netconf_get_config")
async def netconf_get_config(
    body: Optional[GetConfigRequest] = Body(None),
    host: Optional[str] = Query(None),
    port: Optional[int] = Query(None),
    timeout_ops: Optional[int] = Query(None),
    username: Optional[str] = Query(None),
    password: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    filter_xml: Optional[str] = Query(None),
):
    req = _merge_to_model(
        GetConfigRequest, body,
        host=host, port=port, timeout_ops=timeout_ops, username=username, password=password,
        source=source, filter_xml=filter_xml
    )
    dev = _device(req)
    async with AsyncNetconfDriver(**dev) as conn:
        if req.filter_xml:
            rsp = await conn.get_config(source=req.source, filter_=req.filter_xml)
        else:
            rsp = await conn.get_config(source=req.source)
        return {"ok": True, "source": req.source, "result": rsp.result}

@app.post("/netconf/edit-config", operation_id="netconf_edit_config")
async def netconf_edit_config(
    body: Optional[EditConfigRequest] = Body(None),
    host: Optional[str] = Query(None),
    port: Optional[int] = Query(None),
    timeout_ops: Optional[int] = Query(None),
    username: Optional[str] = Query(None),
    password: Optional[str] = Query(None),
    target: Optional[str] = Query(None),
    config_xml: Optional[str] = Query(None),
    default_operation: Optional[str] = Query(None),
    test_option: Optional[str] = Query(None),
    error_option: Optional[str] = Query(None),
):
    req = _merge_to_model(
        EditConfigRequest, body,
        host=host, port=port, timeout_ops=timeout_ops, username=username, password=password,
        target=target, config_xml=config_xml, default_operation=default_operation,
        test_option=test_option, error_option=error_option
    )
    dev = _device(req)
    async with AsyncNetconfDriver(**dev) as conn:
        rsp = await conn.edit_config(
            config=req.config_xml,
            target=req.target,
            default_operation=req.default_operation,
            test_option=req.test_option,
            error_option=req.error_option,
        )
        return {"ok": True, "target": req.target, "result": rsp.result}

@app.post("/netconf/commit", operation_id="netconf_commit")
async def netconf_commit(
    body: Optional[CommitRequest] = Body(None),
    host: Optional[str] = Query(None),
    port: Optional[int] = Query(None),
    timeout_ops: Optional[int] = Query(None),
    username: Optional[str] = Query(None),
    password: Optional[str] = Query(None),
    confirmed: Optional[bool] = Query(None),
    confirm_timeout: Optional[int] = Query(None),
    comment: Optional[str] = Query(None),
):
    req = _merge_to_model(
        CommitRequest, body,
        host=host, port=port, timeout_ops=timeout_ops, username=username, password=password,
        confirmed=confirmed, confirm_timeout=confirm_timeout, comment=comment
    )
    dev = _device(req)
    async with AsyncNetconfDriver(**dev) as conn:
        if req.confirmed:
            rpc = f'<commit-configuration confirmed="true" confirm-timeout="{int(req.confirm_timeout)}">'
            if req.comment:
                rpc += f"<log>{_escape(req.comment)}</log>"
            rpc += "</commit-configuration>"
            rsp = await conn.rpc(rpc)
        else:
            rpc = "<commit-configuration>"
            if req.comment:
                rpc += f"<log>{_escape(req.comment)}</log>"
            rpc += "</commit-configuration>"
            rsp = await conn.rpc(rpc)
        return {"ok": True, "result": rsp.result}

@app.post("/netconf/rpc", operation_id="netconf_rpc")
async def netconf_rpc(
    body: Optional[RpcRequest] = Body(None),
    host: Optional[str] = Query(None),
    port: Optional[int] = Query(None),
    timeout_ops: Optional[int] = Query(None),
    username: Optional[str] = Query(None),
    password: Optional[str] = Query(None),
    rpc_xml: Optional[str] = Query(None),
):
    req = _merge_to_model(
        RpcRequest, body,
        host=host, port=port, timeout_ops=timeout_ops, username=username, password=password,
        rpc_xml=rpc_xml
    )
    dev = _device(req)
    async with AsyncNetconfDriver(**dev) as conn:
        rsp = await conn.rpc(req.rpc_xml)
        return {"ok": True, "rpc": req.rpc_xml, "result": rsp.result}
