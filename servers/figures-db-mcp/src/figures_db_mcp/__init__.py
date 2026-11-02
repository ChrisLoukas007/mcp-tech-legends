"""figures-db-mcp: read-only MCP access to the tech legends database.

Read the files in the order they were built; each one answers one question:
    1. config.py    WHERE is the database, and how strict are the limits?
    2. models.py    WHAT shape does each answer have?
    3. backend.py   HOW is the data fetched from Postgres? (no MCP here)
    4. tools.py     WHAT may the model ask for, with which inputs?
    5. server.py    WHO is this server? (name, instructions, resources, prompt)
    6. __main__.py  HOW does it all start?
"""
