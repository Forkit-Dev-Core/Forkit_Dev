"""Allow official hooks to invoke the installed interpreter without PATH lookup."""
from .cli import main

raise SystemExit(main())
