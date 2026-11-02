"""agent-cli: a custom MCP host. One Claude conversation, one MCP client per server.

A host is the app the user talks to. It owns the LLM and opens one MCP client per server; the
servers own the data and the security checks. Read the files in this order:
    1. config.py       WHICH model, WHICH servers, and HOW to reach them?
    2. connections.py  HOW do we connect to every server and build one tool list?
    3. loop.py         HOW does one question become model calls and tool calls?
    4. auth.py         HOW do we get a separate token per server? (HTTP mode only)
    5. __main__.py     HOW does it all start?
"""
