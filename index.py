#!/usr/bin/env python3
"""Dida365 CLI skill entrypoint."""

import sys
from cli import main

# Windows 下强制 UTF-8 输出编码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

if __name__ == "__main__":
    main()
