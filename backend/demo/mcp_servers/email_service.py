from datetime import UTC, datetime

from mcp.server.mcpserver import MCPServer

# Nothing is ever sent: emails land in this in-memory outbox, visible at GET /outbox.
OUTBOX: list[dict] = []


def build() -> MCPServer:
    mcp = MCPServer(name="email", instructions="Mock email service. Messages are queued, never delivered.")

    @mcp.tool()
    def send_email(to: str, subject: str, body: str) -> dict:
        """Send an email."""
        message = {"id": f"m-{len(OUTBOX) + 1}", "to": to, "subject": subject, "body": body,
                   "queued_at": datetime.now(UTC).isoformat(timespec="seconds")}
        OUTBOX.append(message)
        return {"status": "queued", "id": message["id"]}

    return mcp
