"""mcp_kit: the rules every MCP server in this repo follows, written once.

A server only says WHAT it offers (tools, backend); this kit decides HOW every call is checked,
recorded and served. Fix a rule here and all three servers get the fix. Read in this order:
    1. settings.py       WHAT can be configured, for every server?
    2. observability.py  HOW does a server report what it does? (logs, metrics, traces)
    3. audit.py          HOW is every call recorded, allowed or denied?
    4. policy.py         WHO may do WHAT? The gate every tool call passes (the key file)
    5. auth.py           IS this token real, and is it for this server? (HTTP only)
    6. server.py         HOW do the pieces above become a running server?
    7. testing.py        HOW do tests pretend to be a user without Keycloak?
"""
