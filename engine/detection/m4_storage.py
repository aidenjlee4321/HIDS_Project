"""Bounded private inventory of the active M4 store and retained backups."""
import stat
from pathlib import Path
from engine.detection.m4_handoff import private
from engine.detection.m4_pilot import Invalid
from engine.ingestion import m3_storage

MAX_NODES=4096
MAX_DEPTH=4


def inventory(directory):
    """Yield files without following links or opening payloads; fail closed."""
    root=Path(directory);pending=[(root,0)];nodes=0
    while pending:
        parent,depth=pending.pop();private(parent,directory=True)
        for entry in parent.iterdir():
            nodes+=1
            if nodes>MAX_NODES:raise Invalid('M4 state inventory bound exceeded')
            info=entry.lstat()
            if depth==0 and (entry.name not in ('store','backups') or not stat.S_ISDIR(info.st_mode)):
                raise Invalid('unexpected M4 state entry')
            if stat.S_ISDIR(info.st_mode):
                if depth>=MAX_DEPTH:raise Invalid('M4 state inventory depth exceeded')
                private(entry,directory=True);pending.append((entry,depth+1))
            else:
                private(entry);yield entry


def aggregate(directory):
    total=0
    for path in inventory(directory):
        info=path.stat();total+=max(info.st_size,info.st_blocks*512)
    return total


class Guard(m3_storage.Guard):
    def _inventory(self):
        return inventory(self.directory.parent)
