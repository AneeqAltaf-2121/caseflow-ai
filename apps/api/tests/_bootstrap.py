"""Import side effect only: must run before any `app.*` module is
imported. app/jobs/__init__.py reads ENVIRONMENT at import time to choose
between a real RedisBroker and an in-memory StubBroker, and Dramatiq actors
bind to whatever broker is global at *their* import time — so this has to
win the race against every other import in conftest.py, which is why it's
its own module imported first rather than an inline statement (keeps every
import in conftest.py itself lint-clean, at the top, in one block).
"""

import os

os.environ.setdefault("ENVIRONMENT", "test")
