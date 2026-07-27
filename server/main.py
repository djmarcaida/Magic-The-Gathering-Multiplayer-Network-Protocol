import argparse
import socket
import sys
from common.framing import send_pdu, recv_pdu

DEFAULT_PORT = 4444  # Default specified in RFC Section 5.1[cite: 1]


class GameServer:
    def __init__(self, port: int = DEFAULT_PORT, verbose: bool = False):
        self.port = port
        self.verbose = verbose
        self.clients = []  # Stores (socket, address, player_id)
        self.server_seq_num = 1  # Server monotonically increasing sequence counter[cite: 1]

    def start(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("0.0.0.0", self.port))
        server_sock.listen(2)

        print(f"[*] MTGNP Game Server listening on port {self.port}...")
        print(f"[*] Verbose mode is {'ENABLED' if self.verbose else 'DISABLED'}")

        # Accept exactly two client connections[cite: 1]
        while len(self.clients) < 2:
            conn, addr = server_sock.accept()
            print(f"[+] Player connection accepted from {addr}")
            self.clients.append({"sock": conn, "addr": addr, "player_id": None})

        print("[*] Two clients seated. Refusing further connections.")
        server_sock.close()  # Refuse any 3rd connection attempts per spec[cite: 1]

        self.handle_lobby()

    def handle_lobby(self):
        """Processes initial PLAYER_READY PDUs in LOBBY state[cite: 1]."""
        ready_count = 0

        for client in self.clients:
            try:
                pdu = recv_pdu(client["sock"], verbose=self.verbose, label=f"RECV from {client['addr']}")

                if pdu.get("type") == "PLAYER_READY":
                    player_id = pdu.get("player_id")
                    deck_list = pdu.get("deck_list", [])

                    # Basic spec validations[cite: 1]
                    if not (1 <= len(deck_list) <= 50):  #[cite: 1]
                        err_pdu = {
                            "type": "ERROR",
                            "seq_num": pdu.get("seq_num", 1),
                            "code": "ILLEGAL_DECK",
                            "message": f"Deck contains {len(deck_list)} cards; must be 1 to 50.",
                            "rejected_action": pdu,
                        }
                        send_pdu(client["sock"], err_pdu, verbose=self.verbose, label="SEND ERROR")
                        continue

                    client["player_id"] = player_id
                    ready_count += 1

                    # Send lobby update back to client[cite: 1]
                    update_pdu = {
                        "type": "GAME_STATE_UPDATE",
                        "seq_num": self.server_seq_num,
                        "state": {
                            "phase": "LOBBY",
                            "players_ready": ready_count,
                            "waiting_for": ["player_2"] if ready_count == 1 else [],
                        },
                    }
                    self.server_seq_num += 1
                    send_pdu(client["sock"], update_pdu, verbose=self.verbose, label="SEND LOBBY UPDATE")

            except Exception as e:
                print(f"[-] Connection error with client: {e}")
                sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MTGNP Game Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose PDU logging")
    args = parser.parse_args()

    server = GameServer(port=args.port, verbose=args.verbose)
    server.start()