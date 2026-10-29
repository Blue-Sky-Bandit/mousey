"""Entry point for the packaged Mousey.exe."""

import sys

from g502.gui.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
