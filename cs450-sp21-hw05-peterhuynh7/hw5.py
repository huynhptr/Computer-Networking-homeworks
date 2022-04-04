"""
Where solution code to HW5 should be written.  No other files should
be modified.
"""

import socket
import io
import time
import homework5
import homework5.logging


def send(sock: socket.socket, data: bytes):
    """
    Implementation of the sending logic for sending data over a slow,
    lossy, constrained network.

    Args:
        sock -- A socket object, constructed and initialized to communicate
                over a simulated lossy network.
        data -- A bytes object, containing the data to send over the network.
    """
    logger = homework5.logging.get_logger("hw5-sender")

    # one-bit header contains the sequence number to aid retransmission
    # and duplicate
    next_seq = "0"
    header_size = len(next_seq.encode())

    alpha = 0.125  # typical value for calculating estimated_rtt
    beta = 0.25  # typical value for calculating dev_rtt

    # initial values
    estimated_rtt = 0
    dev_rtt = 0
    timeout_interval = 1.5  # arbitrary but should not be too low

    # size of payload after subtracting MAX_PACKET (1400 bytes) by header size
    chunk_size = homework5.MAX_PACKET - header_size

    pause = .001  # let network rest in case delay = 0
    offsets = range(0, len(data), chunk_size)
    first_packet = True  # flag to set estimated_rtt and dev_rtt the first time
    for chunk in [data[i:i + chunk_size] for i in offsets]:
        sock.settimeout(timeout_interval)

        # create packet by concatenating header and payload
        packet = next_seq.encode() + chunk

        sock.send(packet)

        # flag to check if the current packet was resent previously
        # in order to decide sample_rtt calculation
        was_resent = False

        start_time = time.time()  # start timer for sample_rtt calculation

        # update sequence number
        last_seq = next_seq
        next_seq = "0" if last_seq == "1" else "1"

        received_ack = False
        # wait until the correct Ack received, then send the next payload chunk
        while not received_ack:
            try:
                ack = sock.recv(homework5.MAX_PACKET)

                # split data into sequence number and payload
                seq_num, payload = ack[:1].decode(), ack[1:]
                logger.info("Ack seq#%s payload:%s timeout:%f.2", seq_num,
                            payload, timeout_interval)

                if seq_num == last_seq:  # correct Ack
                    received_ack = True

                    # if this is not a packet that was resent,
                    # calculate timeout interval
                    if not was_resent:
                        sample_rtt = time.time() - start_time
                        if first_packet:
                            first_packet = False
                            # typical values for the first time calculation
                            estimated_rtt = sample_rtt
                            dev_rtt = sample_rtt/2
                        else:
                            estimated_rtt = ((1 - alpha)*estimated_rtt +
                                             alpha*sample_rtt)
                            dev_rtt = ((1 - beta)*dev_rtt +
                                       beta*abs(sample_rtt - estimated_rtt))
                        timeout_interval = estimated_rtt + 4*dev_rtt

            except socket.timeout:
                logger.info("Timeout for ACK, resending a packet...")
                sock.send(packet)
                was_resent = True

        logger.info("Pausing for %f seconds", round(pause, 2))
        time.sleep(pause)


def recv(sock: socket.socket, dest: io.BufferedIOBase) -> int:
    """
    Implementation of the receiving logic for receiving data over a slow,
    lossy, constrained network.

    Args:
        sock -- A socket object, constructed and initialized to communicate
                over a simulated lossy network.

    Return:
        The number of bytes written to the destination.
    """
    logger = homework5.logging.get_logger("hw5-receiver")

    expect_seq = "0"  # first sequence number
    ack = ""  # place holder for acknowledgement
    num_bytes = 0  # size of payload received so far
    while True:
        data = sock.recv(homework5.MAX_PACKET)
        if not data:
            break
        logger.info("Received %d bytes", len(data))

        last_seq = expect_seq

        # split sequence number and payload
        seq_num, payload = data[:1].decode(), data[1:]

        if seq_num == expect_seq:  # correct sequence number

            # simulate passing data to the above layer
            dest.write(payload)
            num_bytes += len(payload)
            dest.flush()

            ack = last_seq.encode()  # create acknowledgement

            # update sequence number
            expect_seq = "0" if last_seq == "1" else "1"

        sock.send(ack)  # send Ack

    return num_bytes
