"""Browser initiated OAuth; native CLI alone stores and refreshes credentials."""
import os
from pathlib import Path
import pty
import re
import secrets
import select
import subprocess
import sys
import threading
import time


class BrowserAuthorization:
    def __init__(self, root):
        self.root = Path(root)
        self._lock = threading.RLock()
        self._process = None
        self._fd = None
        self._state = 'idle'
        self._session = ''
        self._url = ''
        self._expires = 0

    def state(self):
        with self._lock:
            if self._state in {'starting', 'waiting', 'verifying'} and time.monotonic() >= self._expires:
                self.close();self._state = 'expired'
            return {'state': self._state, 'session': self._session,
                    'url': self._url if self._state == 'waiting' else '',
                    'message': {'idle':'', 'starting':'正在准备授权页面', 'waiting':'打开极空间网页完成授权，再把一次性授权码粘贴到下方',
                        'verifying':'正在验证授权码', 'complete':'授权已完成', 'failed':'授权未完成，请重新开始',
                        'expired':'授权页面已过期，请重新开始'}.get(self._state, '')}

    def active(self):
        return self.state()['state'] in {'starting', 'waiting', 'verifying'}

    def start(self):
        with self._lock:
            if self.active():return {'success': True, **self.state()}
            if not (self.root / 'zspace-cli').is_file():return {'success':False, 'message':'请先安装 NAS 授权工具'}
            self.close()
            master, slave = pty.openpty()
            try:
                self._process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('auth_worker.py')), str(self.root / 'zspace-cli')],
                    stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
                    env=dict(os.environ, ZSPACE_CLI_HOME=str(self.root / 'profile')))
            except OSError:
                os.close(master);return {'success':False, 'message':'无法启动授权，请检查工具安装'}
            finally:os.close(slave)
            self._fd = master;self._state = 'starting';self._url = '';self._session = secrets.token_urlsafe(24);self._expires = time.monotonic() + 600
            threading.Thread(target=self._read, args=(self._process, master, self._session), daemon=True).start()
            return {'success': True, **self.state()}

    def _read(self, process, fd, session):
        # Deliberately retain only the public authorize URL, never CLI output.
        tail = b''
        try:
            while process.poll() is None and time.monotonic() < self._expires:
                ready, _, _ = select.select([fd], [], [], 0.5)
                if not ready:continue
                chunk = os.read(fd, 4096)
                if not chunk:break
                tail = (tail + chunk)[-8192:]
                match = re.search(rb'https://oauth\.zconnect\.cn/wbui/authorize\?[^\s\x1b<>]+', tail)
                if match:
                    from urllib.parse import urlsplit, parse_qs
                    url = match[0].decode('ascii', errors='ignore');params = parse_qs(urlsplit(url).query)
                    if params.get('client_id') == ['ZspCli'] and len(params.get('state', [''])[0]) >= 8:
                        with self._lock:
                            if session == self._session and self._state == 'starting':self._url = url;self._state = 'waiting'
                # Do not accumulate stdout that could contain an echoed code.
                if self._state == 'verifying':tail = b''
            if process.poll() is None:process.terminate()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        finally:
            with self._lock:
                if session == self._session:
                    self._state = 'complete' if process.returncode == 0 else 'failed'
                    self._url = ''
                    if self._fd == fd:
                        try:os.close(fd)
                        except OSError:pass
                        self._fd = None

    def submit(self, session, code):
        with self._lock:
            if self.state()['state'] != 'waiting' or not secrets.compare_digest(str(session), self._session):
                return {'success':False, 'message':'授权已过期，请重新开始'}
            if not isinstance(code, str) or not 1 <= len(code.strip()) <= 4096 or any(ord(c) < 32 for c in code.strip()):
                return {'success':False, 'message':'请输入网页给出的一次性授权码'}
            import termios
            attrs = termios.tcgetattr(self._fd);attrs[3] &= ~termios.ECHO;termios.tcsetattr(self._fd, termios.TCSANOW, attrs)
            self._state = 'verifying'
            os.write(self._fd, code.strip().encode() + b'\n')
            return {'success':True, 'state':'verifying', 'message':'正在验证授权码'}

    def close(self):
        with self._lock:
            self._session = ''
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:self._process.kill()
            if self._fd is not None:
                try:os.close(self._fd)
                except OSError:pass
            self._fd = None;self._process = None;self._state = 'idle';self._url = ''
