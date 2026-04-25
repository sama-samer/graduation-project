#!/usr/bin/env python3
"""
receiver_compressed.py
Opus decoding + WAV save
"""

import argparse
import struct
import threading
import time
import wave
import os
import paho.mqtt.client as mqtt
import opuslib

# -----------------------
SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_DURATION_MS = 20
CHUNK = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)

VER = 1
HEADER_STRUCT = struct.Struct("!BI")
HEADER_SIZE = HEADER_STRUCT.size

decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)

received_frames = []
lock = threading.Lock()

record_start_time = None
total_bytes_received = 0

# -----------------------
class VoiceReceiver:
    def __init__(self, broker, port, my_number):
        self.my_number = my_number
        self.signal_topic = f"pbx/voice/signal/{my_number}"
        self.live_topic = f"pbx/voice/live/{my_number}"

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.connect(broker, port)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, rc):
        client.subscribe(self.signal_topic)
        client.subscribe(self.live_topic)
        print("[RX] Ready")

    def on_message(self, client, userdata, msg):
        global record_start_time, total_bytes_received

        if msg.topic == self.signal_topic:
            print("[CALL] Incoming call")
            client.publish(f"pbx/voice/ack/{msg.payload.decode().split(':')[1]}", "RECEIVING")
            return

        if msg.topic == self.live_topic:
            if len(msg.payload) < HEADER_SIZE:
                return

            ver, seq = HEADER_STRUCT.unpack(msg.payload[:HEADER_SIZE])
            if ver != VER:
                return

            compressed = msg.payload[HEADER_SIZE:]
            decoded = decoder.decode(compressed, CHUNK)

            with lock:
                received_frames.append(decoded)

            total_bytes_received += len(decoded)

            if record_start_time is None:
                record_start_time = time.time()

# -----------------------
def save_wav(filename):
    audio_data = b''.join(received_frames)

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)

    duration = len(audio_data) / (SAMPLE_RATE * 2)
    size_mb = len(audio_data) / (1024*1024)

    print("\n================================")
    print("[SAVE] Recording Finished")
    print(f"[SAVE] Duration: {duration:.2f} sec")
    print(f"[SAVE] Size: {len(audio_data)} bytes ({size_mb:.2f} MB)")
    print("================================")


# -----------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", required=True)
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--listen", required=True)
    parser.add_argument("--outfile", default="rx-comp.wav")
    args = parser.parse_args()

    receiver = VoiceReceiver(args.broker, args.port, args.listen)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        save_wav(args.outfile)
