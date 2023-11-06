import socket
import selectors
import uuid
import sys

sel = selectors.DefaultSelector()


class Connection:
    def __init__(self, mgr, sock: socket.socket, remote_addr) -> None:
        self._mgr = mgr
        self._socket = sock
        self._remote_addr = remote_addr
        self._nick = uuid.uuid4().hex[:6]

        self._socket.setblocking(False)
        sel.register(self._socket, selectors.EVENT_READ, self)

        self._wait_send = []

    def handle(self, events):
        if events & selectors.EVENT_READ:
            self.read()
        else:
            self.write_slow()

    def read(self):
        while True:
            try:
                buf = self._socket.recv(1024 * 1024)
                if len(buf) == 0:
                    self.cleanup()
                    break
                else:
                    self.process_msg(
                        buf
                    )  # TODO: This seems inconsistent with using while to read the socket
            except BlockingIOError:
                break

    def process_msg(self, msg: bytes):
        decoded = msg.decode("utf8")
        if decoded[0] == "/":
            self.process_command(decoded)
        else:
            self._mgr.broadcast_but(msg, self)

    def process_command(self, command: str):
        cmd = command.split()
        if cmd[0] == "/nick":
            if len(cmd) != 1:
                self._nick = cmd[1]
        else:
            self.write_fast("Unsupported command\n".encode("utf8"))

    def write_fast(self, msg: bytes):
        if len(self._wait_send) != 0:
            self._wait_send.append(msg)
            return
        nsent = 0
        try:
            nsent = self._socket.send(msg)
        except BlockingIOError:
            self._wait_send.append(msg[nsent:])
            sel.modify(self._socket, selectors.EVENT_READ | selectors.EVENT_WRITE)

    # useless
    def write_slow(self):
        n = len(self._wait_send)
        i = 0
        while i < n:
            buf = self._wait_send[i]
            nsent = 0
            try:
                nsent = self._socket.send(buf)
            except BlockingIOError:
                self._wait_send[i] = buf[nsent:]
                break
            i += 1
        if i == n:
            sel.modify(self._socket, selectors.EVENT_READ)
            return
        self._wait_send = self._wait_send[i:]

    def cleanup(self):
        self._socket.close()
        self.unregister()
        self._mgr.remove(self)

    def unregister(self):
        sel.unregister(self._socket)

    @property
    def nickname(self):
        return self._nick


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[Connection] = []

    def add(self, sock: socket.socket, remote_addr):
        conn = Connection(self, sock, remote_addr)
        self._connections.append(conn)

    def remove(self, conn: Connection):
        self._connections.remove(conn)

    def close(self):
        for conn in self._connections:
            conn.cleanup()

    def broadcast_but(self, msg: bytes, sent_from: Connection):
        msg = sent_from.nickname.encode("utf8") + b": " + msg
        for conn in self._connections:
            if conn == sent_from:
                continue
            conn.write_fast(msg)


cm = ConnectionManager()


def accept(key: selectors.SelectorKey):
    assert isinstance(key.fileobj, socket.socket)
    sock = key.fileobj
    conn, addr = sock.accept()
    print(f"connection from {addr}")
    cm.add(conn, addr)


if __name__ == "__main__":
    listen_sock = socket.socket()
    listen_sock.bind(("localhost", 9900))
    listen_sock.listen(512)
    listen_sock.setblocking(False)
    sel.register(listen_sock, selectors.EVENT_READ, accept)
    while True:
        try:
            events = sel.select()
            for key, mask in events:
                if key.fd == listen_sock.fileno():
                    cb = key.data
                    cb(key)
                else:
                    conn: Connection = key.data
                    conn.handle(mask)
        except KeyboardInterrupt:
            cm.close()
            sel.close()
            sys.exit(1)
