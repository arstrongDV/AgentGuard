from datetime import UTC, datetime

from mcp.server.mcpserver import MCPServer

from demo.mcp_servers.data import BALANCES, FILES

# Executed transfers, for the demo narrative ("nothing left the bank").
LEDGER: list[dict] = []


def build() -> MCPServer:
    mcp = MCPServer(name="bank", instructions="Mock core-banking API.")

    @mcp.tool()
    def get_balance(account_id: str) -> dict:
        """Get the balance of an account (e.g. acc-001)."""
        if account_id not in BALANCES:
            return {"error": f"account {account_id} not found"}
        return {"account_id": account_id, "balance": BALANCES[account_id], "currency": "EUR"}

    @mcp.tool()
    def transfer_money(to_iban: str, amount: float, from_account: str = "acc-001", currency: str = "EUR") -> dict:
        """Transfer money from one of our accounts to an IBAN."""
        entry = {"id": f"tx-{len(LEDGER) + 1}", "from_account": from_account, "to_iban": to_iban, "amount": amount,
                 "currency": currency, "executed_at": datetime.now(UTC).isoformat(timespec="seconds")}
        LEDGER.append(entry)
        BALANCES[from_account] = BALANCES.get(from_account, 0.0) - amount
        return {"status": "executed", **entry}

    @mcp.tool()
    def list_files(path: str) -> dict:
        """List report files in a directory. (Deliberately naive: shows why tool arguments need checking.)"""
        # Never touches the real filesystem: the attack is stopped (or not) at the gateway.
        return {"path": path, "files": FILES.get(path.rstrip("/") or "/", [])}

    return mcp
