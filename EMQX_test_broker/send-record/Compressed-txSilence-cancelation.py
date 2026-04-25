#!/usr/bin/env python3

import threading
import struct
import time
import socket
import numpy as np
import sounddevice as sd
import paho.mqtt.client as mqtt
import opuslib

# ==========================
# AUTO CONFIG
# ==========================
BROKER = socket.gethostbyname(socket.gethostname())
PORT = 1884

# ===== METHOD 1: 8kHz =====
SAMPLE_RATE = 8000
CHANNELS = 1
CHUNK = int(SAMPLE_RATE * 20 / 1000)
BITRATE = 16000

VER = 1
HEADER_STRUCT = struct.Struct("!BI")

encoder = opuslib.Encoder(SAMPLE_RATE, CHANNELS, opuslib.APPLICATION_VOIP)
encoder.bitrate = BITRATE
encoder.vbr = True  # Better compression automatically

# ==========================
class MqttVoiceSender:
    def __init__(self, my_number):
        self.client = mqtt.Client()
        self.my_number = my_number
        self.ack_topic = f"pbx/voice/ack/{self.my_number}"

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.connect(BROKER, PORT)
        self.client.loop_start()

        self.received_ack_event = threading.Event()

    def on_connect(self, client, userdata, flags, rc):
        client.subscribe(self.ack_topic)

    def on_message(self, client, userdata, msg):
        print("[ACK]", msg.payload.decode())
        self.received_ack_event.set()

    def publish_start(self, dest):
        self.client.publish(f"pbx/voice/signal/{dest}", f"START:{self.my_number}")

    def publish_end(self, dest):
        self.client.publish(f"pbx/voice/signal/{dest}", f"END:{self.my_number}")

    def publish_audio(self, dest, seq, compressed):
        header = HEADER_STRUCT.pack(VER, seq)
        self.client.publish(f"pbx/voice/live/{dest}", header + compressed)

# ==========================
def run_sender(my_number, dest):
    sender = MqttVoiceSender(my_number)
    sender.publish_start(dest)
    sender.received_ack_event.wait(3)

    tx_seq = 0
    total_bytes_sent = 0
    start_time = time.time()
    lock = threading.Lock()

    def callback(indata, frames, time_info, status):
        nonlocal tx_seq, total_bytes_sent
        pcm = indata.astype(np.int16).tobytes()
        compressed = encoder.encode(pcm, CHUNK)

        with lock:
            seq = tx_seq
            tx_seq = (tx_seq + 1) & 0xFFFFFFFF

        sender.publish_audio(dest, seq, compressed)
        total_bytes_sent += len(compressed)

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK,
            callback=callback):

            while True:
                time.sleep(0.5)

    except KeyboardInterrupt:
        sender.publish_end(dest)

        duration = time.time() - start_time
        size_mb = total_bytes_sent / (1024 * 1024)

        print("\n================================")
        print("[TX] Recording Finished")
        print(f"[TX] Duration: {duration:.2f} sec")
        print(f"[TX] Size: {total_bytes_sent} bytes ({size_mb:.2f} MB)")
        print("================================")

        sender.client.loop_stop()
        sender.client.disconnect()

if __name__ == "__main__":
    my_number = input("Enter your number: ")
    destination = input("Enter destination number: ")
    run_sender(my_number, destination)
