"""The fake MySQL server leaves the TLS handshake on the socket after SSLRequest."""
import socket
import unittest

from mysql_check import Session


class PacketBoundary(unittest.TestCase):
    def test_sslrequest_and_clienthello_in_one_write(self):
        client, server = socket.socketpair()
        with client, server:
            client.settimeout(1)
            server.settimeout(1)
            request = b'\x00' * 32
            hello = b'\x16\x03\x01\x00\x05hello'
            client.sendall(len(request).to_bytes(3, 'little') + b'\x01' + request + hello)
            session = Session(None, server)
            self.assertEqual(session.recv(), request)
            self.assertEqual(session.seq, 2)
            self.assertEqual(session.buf, b'')
            self.assertEqual(server.recv(len(hello)), hello)

    def test_consecutive_mysql_packets(self):
        client, server = socket.socketpair()
        with client, server:
            client.settimeout(1)
            server.settimeout(1)
            client.sendall(b'\x03\x00\x00\x00one\x03\x00\x00\x01two')
            session = Session(None, server)
            self.assertEqual(session.recv(), b'one')
            self.assertEqual(session.seq, 1)
            self.assertEqual(session.recv(), b'two')
            self.assertEqual(session.seq, 2)


if __name__ == '__main__':
    unittest.main()
