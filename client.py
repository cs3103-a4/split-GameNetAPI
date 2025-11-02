import socket
import struct
import time
import threading

class HUDPClient:
    HEADER_FORMAT = '<BQQ'
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    ACK_FORMAT = '<BQ'
    ACK_SIZE = struct.calcsize(ACK_FORMAT)
    
    TIMEOUT = 0.1
    MAX_THRESHOLD = 0.2

    def __init__(self, host, port):
        self.addr = (host, port)
        self.seqno = 0
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(0.1)
        
        self.running = True
        self.pending_packets = {}

        threading.Thread(target=self._ack_listener, daemon=True).start()
        threading.Thread(target=self._retransmit_checker, daemon=True).start()

        self.metrics = {
            'packets_sent': {'reliable': 0, 'unreliable': 0},
            'packets_acked': 0,
            'retransmissions': 0,
            'latencies': [],
            'bytes_sent': 0
        }

    def send_message(self, payload, isReliable=False):
        timestamp_ms = int(time.time() * 1000)
        channel_type = 0 if isReliable else 1

        header_bytes = struct.pack(
            HUDPClient.HEADER_FORMAT,
            channel_type,
            self.seqno,
            timestamp_ms
        )

        payload_bytes = payload.encode('utf-8')
        packet = header_bytes + payload_bytes

        self.socket.sendto(packet, self.addr)
        print(f"Sent {'reliable' if isReliable else 'unreliable'} packet {self.seqno}")

        if isReliable:
            self.pending_packets[self.seqno] = {
                'packet': packet,
                'send_time': time.time(),
                'retries': 0
            }

        self.seqno += 1

        self.metrics['bytes_sent'] += len(packet)
        if isReliable:
            self.metrics['packets_sent']['reliable'] += 1
        else:
            self.metrics['packets_sent']['unreliable'] += 1

    def _ack_listener(self):
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
                if len(data) >= struct.calcsize(HUDPClient.ACK_FORMAT):
                    channel_type, ack_seqno = struct.unpack(
                        HUDPClient.ACK_FORMAT,
                        data[:HUDPClient.ACK_SIZE]
                    )
                    
                    if channel_type == 255:
                        if ack_seqno in self.pending_packets:
                            rtt = time.time() - self.pending_packets[ack_seqno]['send_time']
                            self.metrics['latencies'].append(rtt)
                            self.metrics['packets_acked'] += 1
                            del self.pending_packets[ack_seqno]
                            print(f"ACK received for packet {ack_seqno}, RTT: {rtt*1000:.1f}ms")
                            
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error in ACK listener: {e}")
                continue

    def _retransmit_checker(self):
        while self.running:
            time.sleep(0.05)
            current = time.time()
            
            for seqno, info in list(self.pending_packets.items()):
                elapsed = current - info['send_time']
                
                if elapsed > HUDPClient.TIMEOUT:
                    if elapsed > HUDPClient.MAX_THRESHOLD:
                        del self.pending_packets[seqno]
                        print(f"Gave up on packet {seqno} after {elapsed*1000:.1f}ms")
                    else:
                        self.socket.sendto(info['packet'], self.addr)
                        self.metrics['retransmissions'] += 1
                        info['send_time'] = current
                        info['retries'] += 1
                        print(f"Retransmitting packet {seqno} (retry #{info['retries']})")

    def print_metrics(self):
        print("\n" + "="*50)
        print("CLIENT METRICS")
        print("="*50)
        print(f"Packets Sent (Reliable): {self.metrics['packets_sent']['reliable']}")
        print(f"Packets Sent (Unreliable): {self.metrics['packets_sent']['unreliable']}")
        print(f"Packets ACKed: {self.metrics['packets_acked']}")
        print(f"Retransmissions: {self.metrics['retransmissions']}")
        
        if self.metrics['latencies']:
            latencies_ms = [l * 1000 for l in self.metrics['latencies']]
            print(f"RTT Avg: {sum(latencies_ms)/len(latencies_ms):.2f} ms")
            print(f"RTT Min: {min(latencies_ms):.2f} ms")
            print(f"RTT Max: {max(latencies_ms):.2f} ms")
        
        print(f"Bytes Sent: {self.metrics['bytes_sent']}")
        print("="*50 + "\n")

    def close(self):
        self.running = False
        time.sleep(0.2)
        self.socket.close()
        
        
        

if __name__ == "__main__":
    
    client = HUDPClient('127.0.0.1', 65432)
    client.send_message("1", isReliable=True)
    client.send_message("2", isReliable=True)
    client.send_message("3", isReliable=True)
    client.send_message("4", isReliable=True)
    client.send_message("5", isReliable=True)
    client.send_message("6", isReliable=True)
    client.send_message("7", isReliable=True)
    client.send_message("8", isReliable=True)
    client.send_message("9", isReliable=True)
    client.send_message("10", isReliable=True)

    time.sleep(10)
    client.print_metrics()
    client.close()