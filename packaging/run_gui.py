"""Entry point of DroidCommander.exe: the app window (configure + launch)."""
import sys

from droid.__main__ import main

if __name__ == "__main__":
    main(sys.argv[1:] or ["app"])
