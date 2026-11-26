# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2.3"]
# ///
"""A typical MCP server written the way most people write one: Pydantic models, optional fields,
constraints. Checked with `mcp-schema-bridge check` (see README.md in this folder).

Change made after the check: `metadata: dict[str, str]` (an open map, which strict modes of OpenAI
and Claude cannot express) became a list of {key, value} objects."""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

server = MCPServer("crm")


class KeyValue(BaseModel):
    key: str
    value: str


class Contact(BaseModel):
    name: Annotated[str, Field(min_length=1, description="Full name")]
    email: str | None = None
    phone: Annotated[str | None, Field(pattern=r"^\+[1-9]\d{6,14}$", description="E.164 phone number")] = None
    stage: Literal["lead", "customer", "churned"] = "lead"
    metadata: list[KeyValue] = []


@server.tool()
def create_contact(contact: Contact) -> str:
    """Create a contact in the CRM."""
    return f"created {contact.name}"


@server.tool()
def search_contacts(query: Annotated[str, Field(min_length=2)], limit: Annotated[int, Field(ge=1, le=50)] = 10) -> str:
    """Search contacts by name or email."""
    return f"results for {query} (limit {limit})"


if __name__ == "__main__":
    server.run()
