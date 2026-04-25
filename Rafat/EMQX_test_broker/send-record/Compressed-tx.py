#!/usr/bin/env python3
"""
sender_signal_stream_compressed.py
Opus compressed streaming over MQTT
"""

import argparse
import threading
import struct
import time
import numpy as np
import sounddevice as sd
import paho.mqtt.client as mqtt
import opuslib

# -----------------------
# Config (Voice Optimized)
# -----------------------
SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_DURATION_MS = 20
CHUNK = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 320
BITRATE = 24000

VER = 1
HEADER_STRUCT = struct.Struct("!BI")

encoder = opuslib.Encoder(SAMPLE_RATE, CHANNELS, opuslib.APPLICATION_VOIP)
encoder.bitrate = BITRATE

# -----------------------
class MqttVoiceSender:
    def __init__(self, broker, port, my_number):
        self.client = mqtt.Client()
        self.my_number = my_number
        self.ack_topic = f"pbx/voice/ack/{self.my_number}"
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(broker, port, 60)
        self.client.loop_start()
        self.received_ack_event = threading.Event()

    def on_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] Connected rc={rc}")
        client.subscribe(self.ack_topic)

    def on_message(self, client, userdata, msg):
        print(f"[ACK] {msg.payload.decode()}")
        self.received_ack_event.set()

    def publish_start(self, dest):
        topic = f"pbx/voice/signal/{dest}"
        payload = f"START:{self.my_number}"
        self.client.publish(topic, payload.encode())

    def publish_audio(self, dest, seq, compressed):
        topic = f"pbx/voice/live/{dest}"
        header = HEADER_STRUCT.pack(VER, seq)
        self.client.publish(topic, header + compressed)


# -----------------------
def run_sender(broker, port, my_number, dest):
    sender = MqttVoiceSender(broker, port, my_number)
    sender.publish_start(dest)

    print("[INFO] Waiting 3s for ACK...")
    sender.received_ack_event.wait(3)

    tx_seq = 0
    lock = threading.Lock()

    def callback(indata, frames, time_info, status):
        nonlocal tx_seq
        pcm = indata.astype(np.int16).tobytes()
        compressed = encoder.encode(pcm, CHUNK)

        with lock:
            seq = tx_seq
            tx_seq = (tx_seq + 1) & 0xFFFFFFFF

        sender.publish_audio(dest, seq, compressed)

    print("[INFO] Sending compressed audio...")
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=CHUNK,
        callback=callback):

        while True:
            time.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", required=True)
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--from", dest="src", required=True)
    parser.add_argument("--to", dest="dst", required=True)
    args = parser.parse_args()

    run_sender(args.broker, args.port, args.src, args.dst)
