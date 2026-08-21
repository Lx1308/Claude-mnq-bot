"""Einstiegspunkt: ``python -m mcp_server``.

Bewusst minimal - insbesondere ohne Umbiegen von ``sys.stdout``. Die
Begruendung steht in :mod:`mcp_server.server`.
"""

from mcp_server.server import main

if __name__ == "__main__":
    main()
