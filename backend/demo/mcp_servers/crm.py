from mcp.server.mcpserver import MCPServer

from demo.mcp_servers.data import CUSTOMERS


def build() -> MCPServer:
    mcp = MCPServer(name="crm", instructions="Mock CRM with customer records.")

    @mcp.tool()
    def search_customers(query: str) -> list[dict]:
        """Search customers by name, email or id. Returns full customer records."""
        q = query.lower().strip()
        return [c for c in CUSTOMERS if q in c["name"].lower() or q in c["email"] or q == c["id"]]

    @mcp.tool()
    def get_customer(id: str) -> dict:
        """Get one customer record by id (e.g. c-1)."""
        for c in CUSTOMERS:
            if c["id"] == id:
                return c
        return {"error": f"customer {id} not found"}

    return mcp
