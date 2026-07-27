import argparse
import socket
import sys
import threading
import time
from framing import send_pdu, recv_pdu


class MTGClient:
    def __init__(self, host: str, port: int, player_id: str, verbose: bool = False):
        self.host = host
        self.port = port
        self.player_id = player_id
        self.verbose = verbose
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_seq_num = 1
        self.last_priority_seq_num = None  # Tracks current priority token seq_num[cite: 1]

    def connect(self):
        print(f"[*] Connecting to MTGNP server at {self.host}:{self.port}...")
        self.sock.connect((self.host, self.port))
        print("[+] Connected successfully.")

        # Start background receiver thread
        recv_thread = threading.Thread(target=self.receive_loop, daemon=True)
        recv_thread.start()

        # Send initial PLAYER_READY[cite: 1]
        self.send_ready()

        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Exiting client.")

    def send_ready(self):
        """Sends PLAYER_READY with starter deck list[cite: 1]."""
        ready_pdu = {
            "type": "PLAYER_READY",
            "seq_num": self.client_seq_num,
            "player_id": self.player_id,
            "deck_list": [
                "lightning_bolt_001",
                "lightning_bolt_002",
                "shock_001",
                "shock_002",
                "goblin_guide_001",
                "mountain_001",
                "mountain_002",
            ],
        }
        self.client_seq_num += 1
        send_pdu(self.sock, ready_pdu, verbose=self.verbose, label="SEND PLAYER_READY")

    def receive_loop(self):
        """Continuously listens for server PDUs[cite: 1]."""
        while True:
            try:
                pdu = recv_pdu(self.sock, verbose=self.verbose, label="RECV FROM SERVER")
                pdu_type = pdu.get("type")

                # Track sequence numbers from priority or request PDUs for client action echoes[cite: 1]
                if pdu_type in ["PRIORITY_GRANT", "PHASE_TRANSITION", "GAME_STATE_UPDATE"]:
                    self.last_priority_seq_num = pdu.get("seq_num")

                if pdu_type == "PING":
                    # Respond to heartbeats if server pings
                    pong = {"type": "PONG", "seq_num": pdu.get("seq_num"), "timestamp": pdu.get("timestamp")}
                    send_pdu(self.sock, pong, verbose=self.verbose, label="SEND PONG")

            except ConnectionError:
                print("[-] Disconnected from server.")
                sys.exit(0)
            except Exception as e:
                print(f"[-] Error parsing incoming message: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MTGNP Game Client")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host IP")
    parser.add_argument("--port", type=int, default=4444, help="Server port")
    parser.add_argument("--id", type=str, required=True, help="Player ID string")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose PDU logging")
    args = parser.parse_args()

    client = MTGClient(host=args.host, port=args.port, player_id=args.id, verbose=args.verbose)
    client.connect()