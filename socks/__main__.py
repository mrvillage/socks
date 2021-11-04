"""
The MIT License (MIT)

Copyright (c) 2021-present Village

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

import dotenv
from server import Server

dotenv.load_dotenv()  # type: ignore


SOCKS_SECRET = os.getenv("SOCKS_SECRET")


@contextlib.contextmanager
def setup_logging():
    logging.getLogger("socks").setLevel(logging.INFO)
    logger = logging.getLogger()
    try:
        handler = logging.FileHandler(filename="socks.log", encoding="utf-8", mode="a")
        handler.setFormatter(
            logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
        )
        logger.addHandler(handler)
        yield
    finally:
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)


if SOCKS_SECRET is None:
    raise ValueError("No SOCKS_SECRET value in .env file")

loop = asyncio.get_event_loop()
SERVER = Server(SOCKS_SECRET, loop)

with setup_logging():
    SERVER.start()
    loop.run_forever()
