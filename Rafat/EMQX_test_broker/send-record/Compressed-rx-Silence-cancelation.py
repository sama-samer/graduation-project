#!/usr/bin/env python3

import struct
import threading
import time
import wave
import socket
import numpy as np
import subprocess
from datetime import datetime
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

VER = 1
HEADER_STRUCT = struct.Struct("!BI")
HEADER_SIZE = HEADER_STRUCT.size

decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)

received_frames = []
received_lock = threading.Lock()

call_active = False

# ==========================
class VoiceReceiver:
    def __init__(self, my_number):
        self.my_number = my_number
        self.signal_topic = f"pbx/voice/signal/{my_number}"
        self.live_topic = f"pbx/voice/live/{my_number}"

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.connect(BROKER, PORT)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, rc):
        client.subscribe(self.signal_topic)
        client.subscribe(self.live_topic)
        print(f"[RX] Listening on {BROKER}:{PORT}")

    def on_message(self, client, userdata, msg):
        global call_active

        if msg.topic == self.signal_topic:
            message = msg.payload.decode()

            if message.startswith("START"):
                sender_number = message.split(":")[1]
                client.publish(f"pbx/voice/ack/{sender_number}", "RECEIVING")
                call_active = True
                print("[CALL] Recording started")
                return

            if message.startswith("END"):
                print("[CALL] Call ended by TX")
                call_active = False
                save_wav()
                received_frames.clear()
                return

        if msg.topic == self.live_topic and call_active:
            if len(msg.payload) < HEADER_SIZE:
                return

            ver, seq = HEADER_STRUCT.unpack(msg.payload[:HEADER_SIZE])
            if ver != VER:
                return

            compressed = msg.payload[HEADER_SIZE:]
            decoded = decoder.decode(compressed, CHUNK)

            with received_lock:
                received_frames.append(decoded)

# ==========================
def trim_silence(audio_bytes, threshold=500):
    # ===== METHOD 3: Silence Trimming =====
    audio_np = np.frombuffer(audio_bytes, dtype=np.int16)

    mask = np.abs(audio_np) > threshold
    if not np.any(mask):
        return audio_bytes

    first = np.argmax(mask)
    last = len(audio_np) - np.argmax(mask[::-1])
    trimmed = audio_np[first:last]

    return trimmed.astype(np.int16).tobytes()

# ==========================
def save_wav():
    with received_lock:
        audio_data = b''.join(received_frames)

    if not audio_data:
        return

    # ===== METHOD 3 APPLY =====
    audio_data = trim_silence(audio_data)

    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.wav")

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)

    # ===== METHOD 4: FLAC ARCHIVE =====
    flac_name = filename.replace(".wav", ".flac")
    try:
        subprocess.run(["flac", "-f", filename])
        print(f"[ARCHIVE] FLAC saved: {flac_name}")
    except Exception:
        print("[ARCHIVE] FLAC conversion skipped (flac not installed)")

    duration = len(audio_data) / (SAMPLE_RATE * 2)
    size_mb = len(audio_data) / (1024 * 1024)

    print("\n================================")
    print("[SAVE] Recording Finished")
    print(f"[SAVE] File: {filename}")
    print(f"[SAVE] Duration: {duration:.2f} sec")
    print(f"[SAVE] Size: {len(audio_data)} bytes ({size_mb:.2f} MB)")
    print("================================")

# ==========================
if __name__ == "__main__":
    my_number = input("Enter your number: ")
    receiver = VoiceReceiver(my_number)

    while True:
        time.sleep(0.5)
