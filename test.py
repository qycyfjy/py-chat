import random
import socket

for i in range(100):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.connect(('localhost', 9900))
    s.close()