"""FleetPulse MCP server: the same ops tools, exposed over the Model Context
Protocol so any MCP host (Claude Desktop, an IDE) can drive the platform.

Run dev:  mcp dev mcp_server.py
Install:  mcp install mcp_server.py --name FleetPulse
"""

from typing import Any

from mcp.server.mcpserver import MCPServer

from app.db import get_sessionmaker
from app.services import agent_tools

mcp = MCPServer("FleetPulse", version="0.5.0")


def _db():
    return get_sessionmaker()()


@mcp.tool()
def get_fleet_stats(window_hours: int = 24) -> dict[str, Any]:
    """Fleet-wide health: totals, open alerts, silent devices, worst battery and temperature."""
    with _db() as db:
        return agent_tools.get_fleet_stats(db, window_hours)


@mcp.tool()
def list_alerts(
    severity: str | None = None, device: str | None = None, window_hours: int = 24
) -> list[dict[str, Any]]:
    """Open alerts, newest first, optionally filtered by severity or device name."""
    with _db() as db:
        return agent_tools.list_alerts(db, severity, device, window_hours)


@mcp.tool()
def get_device_telemetry(device: str, window_hours: int = 24) -> dict[str, Any]:
    """One device by name: aggregates over the window plus recent raw readings."""
    with _db() as db:
        return agent_tools.get_device_telemetry(db, device, window_hours)


@mcp.tool()
def search_runbooks(query: str) -> list[dict[str, Any]]:
    """Keyword search over the operations runbooks."""
    with _db() as db:
        return agent_tools.search_runbooks(db, query)


if __name__ == "__main__":
    mcp.run()
