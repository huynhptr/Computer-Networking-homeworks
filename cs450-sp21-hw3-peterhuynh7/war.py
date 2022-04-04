"""
war card game client and server
"""
import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
import socket
# import socketserver  # commented out to pass pylint (unused imports)
# import _thread
import sys


# Namedtuples work like classes, but are much more lightweight so they end
# up being faster. It would be a good idea to keep objects in each of these
# for each game which contain the game's state, for instance things like the
# socket, the cards given, the cards still available, etc.
Game = namedtuple("Game",
                  ["sock1", "sock2", "port1", "port2", "cards1", "cards2"])

"""
Mapping indices to cards to make cards comparison more straightforward.
This also trades memory for performance.
"""
index_to_card = {
    0: (2, "clubs"), 1: (3, "clubs"), 2: (4, "clubs"), 3: (5, "clubs"),
    4: (6, "clubs"), 5: (7, "clubs"), 6: (8, "clubs"), 7: (9, "clubs"),
    8: (10, "clubs"), 9: (11, "clubs"),  # Jack
    10: (12, "clubs"),  # Queen
    11: (13, "clubs"),  # King
    12: (14, "clubs"),  # Ace
    13: (2, "diamonds"), 14: (3, "diamonds"), 15: (4, "diamonds"),
    16: (5, "diamonds"), 17: (6, "diamonds"), 18: (7, "diamonds"),
    19: (8, "diamonds"), 20: (9, "diamonds"), 21: (10, "diamonds"),
    22: (11, "diamonds"),  # Jack
    23: (12, "diamonds"),  # Queen
    24: (13, "diamonds"),  # King
    25: (14, "diamonds"),  # Ace
    26: (2, "hearts"), 27: (3, "hearts"), 28: (4, "hearts"), 29: (5, "hearts"),
    30: (6, "hearts"), 31: (7, "hearts"), 32: (8, "hearts"), 33: (9, "hearts"),
    34: (10, "hearts"), 35: (11, "hearts"),  # Jack
    36: (12, "hearts"),  # Queen
    37: (13, "hearts"),  # King
    38: (14, "hearts"),  # Ace
    39: (2, "spades"), 40: (3, "spades"), 41: (4, "spades"), 42: (5, "spades"),
    43: (6, "spades"), 44: (7, "spades"), 45: (8, "spades"), 46: (9, "spades"),
    47: (10, "spades"), 48: (11, "spades"),  # Jack
    49: (12, "spades"),  # Queen
    50: (13, "spades"),  # King
    51: (14, "spades"),  # Ace
}


class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3


class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2


async def readexactly(sock, numbytes, loop):
    """
    Accumulate exactly `numbytes` from `sock` and return those. If EOF is found
    before numbytes have been received, be sure to account for that here or in
    the caller.
    """
    # This function works similarly to StreamReader.readexactly() in a way
    # that it may throw the same Exception.
    received_bytes = await loop.sock_recv(sock, numbytes)
    if len(received_bytes) < numbytes:
        raise asyncio.streams.IncompleteReadError(received_bytes, numbytes)
    return list(received_bytes)


def kill_game(game):
    """
    If either client sends a bad message, immediately nuke the game.
    """
    game.sock1.close()
    game.sock2.close()


def compare_cards(card1, card2):
    """
    Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """
    # Only comparing cards' rank, ignore suite
    rank1 = index_to_card[card1][0]
    rank2 = index_to_card[card2][0]
    return 0 if rank1 == rank2 else (1 if rank1 > rank2 else -1)


def deal_cards():
    """
    Randomize a deck of cards (list of ints 0..51), and return two
    26 card "hands."
    """
    deck = list(range(0, 52))
    random.shuffle(deck)
    logging.debug(deck)
    return deck[:len(deck) // 2], deck[len(deck) // 2:]


def serve_game(host, port):
    """
    Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """
    welcoming_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    welcoming_socket.bind((host, port))
    welcoming_socket.listen()
    welcoming_socket.setblocking(False)
    logging.info("The server is ready to accept connections.")

    loop = asyncio.get_event_loop()

    # Wrap infinite while-loop to an async function so it can be executed
    # by loop.run_until_complete()
    async def accept_clients():
        while True:
            # wait for 2 clients to form a game
            c1_socket, c1_address = await loop.sock_accept(welcoming_socket)
            logging.info("Client with port: %s connected."
                         " Waiting for another client...", c1_address[1])
            c2_socket, c2_address = await loop.sock_accept(welcoming_socket)
            logging.info("Client with port: %s connected."
                         " Game starts.", c2_address[1])

            # create new game
            hand_1, hand_2 = deal_cards()
            new_game = Game(c1_socket, c2_socket,
                            c1_address[1], c2_address[1], hand_1, hand_2)

            # schedule the task to run, but DO NOT wait for it to finish.
            # In other words, fire and forget.
            loop.create_task(start_game(new_game, loop))

    try:
        loop.run_until_complete(accept_clients())
    except KeyboardInterrupt:
        loop.close()


async def start_game(game, loop):
    """
    A coroutine to run a game. When there are 2 clients available,
    a game is started.
    """
    # available cards to ensure clients do not play the same card twice
    # or card not in possession
    c1_available_cards = game.cards1
    c2_available_cards = game.cards2

    # Server receiving "want game" command from clients
    logging.info("Receiving 'want game' command from "
                 "clients %s and %s.", game.port1, game.port2)
    c1_request = await readexactly(game.sock1, 2, loop)
    c2_request = await readexactly(game.sock2, 2, loop)

    if c1_request != [Command.WANTGAME.value, 0] \
            or c2_request != [Command.WANTGAME.value, 0]:
        kill_game(game)
        logging.info("Bad 'want game' message received from "
                     "clients %s and %s. Quitting.", game.port1, game.port2)
        return

    # Server sending "game start" command and dealt cards to clients
    logging.info("Sending 'game start' command to "
                 "clients %s and %s", game.port1, game.port2)
    await loop.sock_sendall(game.sock1,
                            bytes([Command.GAMESTART.value] + game.cards1))
    await loop.sock_sendall(game.sock2,
                            bytes([Command.GAMESTART.value] + game.cards2))

    # running 26 rounds is mandatory
    for i in range(0, 26):
        # expecting 'play card' commands
        c1_request = await readexactly(game.sock1, 2, loop)
        c2_request = await readexactly(game.sock2, 2, loop)

        # extract commands and cards
        c1_cmd, c1_card_play = parse_request(c1_request)
        c2_cmd, c2_card_play = parse_request(c2_request)

        # check for valid commands
        if c1_cmd != Command.PLAYCARD.value \
                or c2_cmd != Command.PLAYCARD.value:
            kill_game(game)
            logging.info("Bad 'play card' commands received from "
                         "clients %s and %s. Quitting.",
                         game.port1, game.port2)
            return

        # check for valid cards played
        if c1_card_play not in c1_available_cards \
                or c2_card_play not in c2_available_cards:
            kill_game(game)
            logging.info("Invalid card detected. Killing game of "
                         "clients %s and %s.", game.port1, game.port2)
            return

        # update available cards for next rounds
        c1_available_cards.remove(c1_card_play)
        c2_available_cards.remove(c2_card_play)

        # evaluate result
        compare_result = compare_cards(c1_card_play, c2_card_play)

        # create 'play result' responses
        c1_response, c2_response = make_play_result_responses(compare_result)

        # building logging string
        result_string = ("It's draw." if compare_result == 0
                         else (f"client{game.port1} wins."
                               if compare_result > 0
                               else f"client{game.port2} wins."))
        logging.info("Round %d: client%s: %s | client%s: %s -> %s",
                     i, game.port1, index_to_card[c1_card_play], game.port2,
                     index_to_card[c2_card_play], result_string)

        # send responses
        await loop.sock_sendall(game.sock1, c1_response)
        await loop.sock_sendall(game.sock2, c2_response)

    # disconnect clients when 26 rounds are played
    kill_game(game)
    logging.info("Game of client %s and "
                 "client %s has finished.", game.port1, game.port2)
    return


def make_play_result_responses(result):
    """
    Create responses for the 2 clients given the result of a round: [-1, 0, 1]
    """
    result_to_response = {
        -1: (bytes([Command.PLAYRESULT.value, Result.LOSE.value]),
             bytes([Command.PLAYRESULT.value, Result.WIN.value])),
        0: (bytes([Command.PLAYRESULT.value, Result.DRAW.value]),
            bytes([Command.PLAYRESULT.value, Result.DRAW.value])),
        1: (bytes([Command.PLAYRESULT.value, Result.WIN.value]),
            bytes([Command.PLAYRESULT.value, Result.LOSE.value]))
    }
    return result_to_response[result]


def parse_request(request):
    """splitting command and payload"""
    return request[0], request[1]


async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    You do not need to change this function.
    """
    async with sem:
        return await client(host, port, loop)


async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    You do not need to change this function.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port, loop=loop)
        # send want game
        writer.write(b"\0\0")
        card_msg = await reader.readexactly(27)
        myscore = 0
        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1
        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"
        logging.debug("Game complete, I %s", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.streams.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0


def main(args):
    """
    launch a client/server
    """
    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return

    loop = asyncio.get_event_loop()

    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        sem = asyncio.Semaphore(1000)
        num_clients = int(args[3])
        clients = [limit_client(host, port, loop, sem)
                   for x in range(num_clients)]

        async def run_all_clients():
            """
            use `as_completed` to spawn all clients simultaneously
            and collect their results in arbitrary order.
            """
            completed_clients = 0
            for client_result in asyncio.as_completed(clients):
                completed_clients += await client_result
            return completed_clients

        res = loop.run_until_complete(
            asyncio.Task(run_all_clients(), loop=loop))
        logging.info("%d completed clients", res)

    loop.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
