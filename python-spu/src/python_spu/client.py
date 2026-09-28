"""Local test driver; starts only its own child and never addresses a server."""
import fcntl
import os
import signal
import socket
import sys
import time
from .transport import Channel

class LocalProcess:
    def __init__(self,stderr,*,module='python_spu.server',arguments=('--cpu-experiment',),channels=2):
        pairs=[socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET) for _ in range(channels)]
        self.log=open(stderr,'wb')
        copies=[fcntl.fcntl(pair[1].fileno(),fcntl.F_DUPFD_CLOEXEC,10) for pair in pairs]
        log_copy=fcntl.fcntl(self.log.fileno(),fcntl.F_DUPFD_CLOEXEC,10)
        actions=[(os.POSIX_SPAWN_DUP2,fd,3+i) for i,fd in enumerate(copies)]
        actions.append((os.POSIX_SPAWN_DUP2,log_copy,2))
        actions.extend((os.POSIX_SPAWN_CLOSE,fd) for fd in copies+[log_copy])
        try:
            self.pid=os.posix_spawn(sys.executable,[sys.executable,'-m',module,*arguments],
                dict(os.environ),file_actions=actions)
        finally:
            for fd in copies+[log_copy]: os.close(fd)
            for _,sock in pairs: sock.close()
        self.channels=[Channel(pair[0],channels==2 and i==1) for i,pair in enumerate(pairs)]
        for channel in self.channels: channel.sock.settimeout(120)
        self.ordinal=0
    def ask(self,body):
        life=self.channels[0]
        life.send({'exchange':{'opener':'harness','ordinal':self.ordinal},'position':'open',
                   'payload':{'kind':'directive','body':body}})
        self.ordinal+=1
        return life.receive()
    def close(self):
        for channel in self.channels: channel.sock.close()
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            done,status=os.waitpid(self.pid,os.WNOHANG)
            if done: break
            time.sleep(.02)
        else:
            os.kill(self.pid,signal.SIGKILL); _,status=os.waitpid(self.pid,0)
        self.log.close()
        return os.waitstatus_to_exitcode(status)
