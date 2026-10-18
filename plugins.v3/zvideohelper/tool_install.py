"""Install only the two verified user-supplied v0.1.4 CLI builds."""
import hashlib
import os
from pathlib import Path
import platform
import tempfile

HASHES = {'x86_64':'acd28ff695aa6c8e173444ad597ed58d671e13eb1ca9f195a7c907efae51ddce',
          'aarch64':'76491ea10603a429e26ceb4a758bc067118bb3e9fec1028b3432c664acb45be4'}


def install_tool(root, content):
    root = Path(root)
    arch = {'amd64':'x86_64','arm64':'aarch64'}.get(platform.machine().lower(),platform.machine().lower())
    if not isinstance(content,bytes) or len(content)>8*1024*1024 or hashlib.sha256(content).hexdigest() != HASHES.get(arch):
        return {'success':False,'message':'请选择原始工具包中与 NAS 架构一致的 Linux v0.1.4 程序；文件校验未通过'}
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=root/'zspace-cli'
    if target.exists():return {'success':False,'message':'授权工具已安装，无需重复导入'}
    fd,name=tempfile.mkstemp(prefix='.install-',dir=root)
    try:
        with os.fdopen(fd,'wb') as handle:handle.write(content);handle.flush();os.fsync(handle.fileno())
        os.chmod(name,0o700);os.link(name,target,follow_symlinks=False)
    finally:os.unlink(name)
    return {'success':True,'message':'授权工具已导入，可以开始网页授权'}
