"""Give the original CLI a controlling terminal without exposing code or tokens."""
import fcntl
import os
from pathlib import Path
import sys
import termios

if __name__ == '__main__':
    # Popen starts a new session. fd 0 is a private PTY, never the MP terminal.
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    attrs = termios.tcgetattr(0)
    attrs[3] &= ~termios.ECHO
    termios.tcsetattr(0, termios.TCSANOW, attrs)
    home = Path(os.environ['ZSPACE_CLI_HOME'])
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = os.open(str(home / 'subtitle-search.lock'), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX)
    os.set_inheritable(lock, True)
    binary = sys.argv[1]
    os.execv(binary, [binary, '--profile', 'zvideohelper', '--credential-store', 'file', '--clear-host', '--mode', 'auto', 'login', '--no-open'])
