import socket
import struct
import threading
import time
from collections import deque

class HUDPServer:
    HEADER_FORMAT = '<BQQ'
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    ACK_FORMAT = '<BQ'
    TIMEOUT_THRESHOLD = 0.2

    def __init__(self, host, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.running = True

        self.reliable_buffer = {}
        self.pending_packets = {}
        self.next_expected_reliable = 0
        self.gap_start_time = None

        self.unreliable_queue = deque([])

        threading.Thread(target=self._packet_receiver, daemon=True).start()
        threading.Thread(target=self._timeout_checker, daemon=True).start()

        self.metrics = {
            'packets_received': {'reliable': 0, 'unreliable': 0},
            'packets_delivered': {'reliable': 0, 'unreliable': 0},
            'packets_skipped': 0,
            'bytes_received': 0,
            'jitter': 0.0,
            'last_arrival': None,
            'last_timestamp': None,
            'start_time': time.time()
        }
        
        print(f"Server listening on {host}:{port}")

    def _packet_receiver(self):
        self.socket.settimeout(0.1)
        
        while self.running:
            try:
                data, client_addr = self.socket.recvfrom(1024)
                
                if len(data) < HUDPServer.HEADER_SIZE:
                    continue

                header = data[:HUDPServer.HEADER_SIZE]
                channel_type, seqno, timestamp = struct.unpack(
                    HUDPServer.HEADER_FORMAT,
                    header
                )
                
                payload = data[HUDPServer.HEADER_SIZE:].decode('utf-8')

                if channel_type == 0:
                    self.metrics['packets_received']['reliable'] += 1
                    self.metrics['bytes_received'] += len(payload)
                    arrival_time = time.time()
                    self._calculate_jitter(timestamp, arrival_time)
                    self._handle_reliable_channel(seqno, payload, client_addr)
                elif channel_type == 1:
                    self._handle_unreliable_channel(seqno, payload)
                    
            except socket.timeout:
                continue
            except Exception as e:
                continue

    def _handle_reliable_channel(self, seqno, payload, client_addr):
        ack = struct.pack(HUDPServer.ACK_FORMAT, 255, seqno)
        self.socket.sendto(ack, client_addr)
        print(f"[RELIABLE] Received packet {seqno}, sent ACK")

        if seqno < self.next_expected_reliable:
            print(f"Duplicate, ignoring")
            return

        if seqno not in self.reliable_buffer:
            self.reliable_buffer[seqno] = payload
            if seqno in self.pending_packets:
                del self.pending_packets[seqno]
            if seqno > self.next_expected_reliable:
                start_time = time.time()
                for i in range(self.next_expected_reliable, seqno):
                    if i in self.pending_packets or i in self.reliable_buffer: 
                        continue
                    self.pending_packets[i] = start_time

    def _handle_unreliable_channel(self, seqno, payload):
        print(f"[UNRELIABLE] Received packet {seqno}")

        self.unreliable_queue.append({
            'seqno': seqno,
            'payload': payload
        })

    def receive_reliable(self):
        if self.next_expected_reliable in self.reliable_buffer:
            payload = self.reliable_buffer[self.next_expected_reliable]
            seqno = self.next_expected_reliable
            
            del self.reliable_buffer[seqno]
            self.next_expected_reliable += 1
            self.gap_start_time = None 
            
            print(f"[APP] Received reliable packet {seqno}: {payload}")
            self.metrics['packets_delivered']['reliable'] += 1
            return (seqno, payload)
        
        return None

    def receive_unreliable(self):
        if self.unreliable_queue:
            packet = self.unreliable_queue.popleft()
            seqno = packet['seqno']
            payload = packet['payload']
            
            print(f"Received unreliable packet {seqno}: {payload}")
            return (seqno, payload)
        
        return None

    def _timeout_checker(self):
        while self.running:
            time.sleep(0.01)
            
            if self.next_expected_reliable in self.pending_packets:
                start_time = self.pending_packets[self.next_expected_reliable]
                elapsed = time.time() - start_time
               
                if elapsed > HUDPServer.TIMEOUT_THRESHOLD:
                    seqno = self.next_expected_reliable
                    del self.pending_packets[seqno]
                    print(f"[RELIABLE] Timeout waiting for packet {seqno}, skipping")
                    self.metrics['packets_skipped'] += 1
                    self.next_expected_reliable = seqno + 1

    def _calculate_jitter(self, timestamp, arrival_time):
        if self.metrics['last_arrival'] is not None:
            D = (arrival_time - self.metrics['last_arrival']) - \
                (timestamp - self.metrics['last_timestamp']) / 1000.0
            self.metrics['jitter'] = self.metrics['jitter'] + (abs(D) - self.metrics['jitter']) / 16.0
        
        self.metrics['last_arrival'] = arrival_time
        self.metrics['last_timestamp'] = timestamp

    def print_metrics(self):
        duration = time.time() - self.metrics['start_time']
        
        print("\n" + "="*50)
        print("SERVER METRICS")
        print("="*50)
        print(f"Packets Received (Reliable): {self.metrics['packets_received']['reliable']}")
        print(f"Packets Received (Unreliable): {self.metrics['packets_received']['unreliable']}")
        print(f"Packets Delivered (Reliable): {self.metrics['packets_delivered']['reliable']}")
        print(f"Packets Skipped: {self.metrics['packets_skipped']}")
        print(f"Bytes Received: {self.metrics['bytes_received']}")
        print(f"Throughput: {self.metrics['bytes_received'] / duration:.2f} bytes/sec")
        print(f"Jitter: {self.metrics['jitter']*1000:.2f} ms")
        
        # Delivery ratio
        reliable_ratio = (self.metrics['packets_delivered']['reliable'] / 
                         self.metrics['packets_received']['reliable'] * 100) \
                         if self.metrics['packets_received']['reliable'] > 0 else 0
        print(f"Reliable Delivery Ratio: {reliable_ratio:.2f}%")
        print("="*50 + "\n")

    def close(self):
        self.running = False
        time.sleep(0.2)
        self.socket.close()


if __name__ == '__main__':
    server = HUDPServer('127.0.0.1', 65432)
    t = 1
    while t <= 6000:
        if t % 1000 == 0:
            server.print_metrics()
        reliable_pkt = server.receive_reliable()
        if reliable_pkt:
            seqno, data = reliable_pkt
            print(f"Reliable data: {data}")

        unreliable_pkt = server.receive_unreliable()
        if unreliable_pkt:
            seqno, data = unreliable_pkt
            print(f"Unreliable data: {data}")

        time.sleep(0.01)
        t += 1
                         