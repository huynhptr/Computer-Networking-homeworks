"""
A program that takes an URL as a commandline argument, send a HTTP request
to the server, and print out the bytes content of the HTTP response.

Functions:

    retrieve_url(string) -> bytes
"""
# import logging
import socket
import sys
import ssl
import re


def retrieve_url(url):
    """
    return bytes of the body of the document at url
    """
    parsed_url = url.split('/', 3)  # parse url string to parts
    protocol = parsed_url[0][:-1]  # extract the protocol: http/https

    # split hostname and port(Ex. www.hostname:80.com)
    name_and_port = parsed_url[2].split(':')
    server_name = name_and_port[0]

    # port 443 for https, or url-specified port. Port 80 if unspecified.
    server_port = 443 if protocol == "https" else \
        int(name_and_port[1]) if len(name_and_port) == 2 else 80

    # extract subdirectory if present
    subdir = parsed_url[3] if len(parsed_url) == 4 else ''

    # use IPv6 and TCP
    client_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        client_socket.connect((server_name, server_port))
    except socket.gaierror:
        return None

    # wrap socket with SSL if protocol is https
    if protocol == "https":
        try:
            client_socket = ssl.create_default_context() \
                .wrap_socket(client_socket, server_hostname=server_name)
        except ssl.SSLError:
            return None

    # construct a http message and send it
    client_socket.send((f'GET /{subdir} HTTP/1.1\r\n'
                        f'Host: {server_name}\r\n'
                        'Connection: close\r\n'
                        '\r\n').encode())

    full_response = b""  # received pieces are accumulated here

    received = client_socket.recv(8192)
    # keep receiving until there is none
    while received:
        full_response = full_response + received
        received = client_socket.recv(8192)

    # extract header and body of response
    header, body = full_response.split(b"\r\n\r\n", 1)

    # extract status code
    status_code = int(header.split(b"\r\n")[0].split(b' ')[1].decode())

    # If status is not 200, reroute when received 301 and
    # content length is not 0. Return None otherwise.
    if status_code != 200:
        if status_code == 301 and \
                int(re.search(r'Content-Length: (.+)\r\n',
                              header.decode()).group(1)) != 0:
            return retrieve_url(re.search(r'Location: (.+)\r\n',
                                          header.decode()).group(1))

        return None

    # If it is chunked encoding, use chunk size to parse message's body
    if str(header).find("Transfer-Encoding: chunked") != -1:
        content = b""
        hex_size_bytes, body = body.split(b"\r\n", 1)  # extract chunk size
        while int(hex_size_bytes, 16) != 0:  # keep reading until size=0
            # append new content
            content = content + body[:int(hex_size_bytes, 16)]

            # plus 2 to skip '\r\n' at chunks ending
            body = body[int(hex_size_bytes, 16) + 2:]

            # get new size and body
            hex_size_bytes, body = body.split(b"\r\n", 1)

        body = content  # new resulting body

    client_socket.close()
    return body


if __name__ == "__main__":
    # pylint: disable=no-member
    sys.stdout.buffer.write(retrieve_url(sys.argv[1]))
