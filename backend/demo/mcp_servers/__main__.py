"""Run the mock MCP servers: CRM :9001, Email :9002, Bank :9003 (streamable HTTP at /mcp).

    python -m demo.mcp_servers                 # all three, on 127.0.0.1
    python -m demo.mcp_servers --host 0.0.0.0  # inside Docker
    python -m demo.mcp_servers --only bank

Servers are stateless and answer with plain JSON, so the AgentGuard proxy can treat every call as
one JSON-RPC request/response. GET /outbox (email) and GET /ledger (bank) show what "really happened".
"""

import argparse
import asyncio
import os

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from demo.mcp_servers import bank, crm, email_service

SERVERS = {"crm": (crm, 9001), "email": (email_service, 9002), "bank": (bank, 9003)}


def build_app(name: str, host: str) -> Starlette:
    module, port = SERVERS[name]
    # DNS-rebinding protection stays on: only the gateway's view of these hosts is accepted.
    extra_hosts = [h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"localhost:{port}", f"127.0.0.1:{port}", f"mcp-{name}:{port}", *extra_hosts],
    )
    app = module.build().streamable_http_app(json_response=True, stateless_http=True, transport_security=security, host=host)

    async def outbox(_: Request) -> JSONResponse:
        return JSONResponse(email_service.OUTBOX)

    async def ledger(_: Request) -> JSONResponse:
        return JSONResponse(bank.LEDGER)

    if name == "email":
        app.router.routes.append(Route("/outbox", outbox))
    if name == "bank":
        app.router.routes.append(Route("/ledger", ledger))
    return app


async def serve(names: list[str], host: str) -> None:
    servers = [
        uvicorn.Server(uvicorn.Config(build_app(name, host), host=host, port=SERVERS[name][1], log_level="warning"))
        for name in names
    ]
    for name in names:
        print(f"mock MCP server '{name}' on http://{host}:{SERVERS[name][1]}/mcp")
    await asyncio.gather(*(s.serve() for s in servers))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--only", choices=list(SERVERS), action="append")
    args = parser.parse_args()
    asyncio.run(serve(args.only or list(SERVERS), args.host))


if __name__ == "__main__":
    main()
