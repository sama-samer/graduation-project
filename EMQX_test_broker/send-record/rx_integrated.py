#!/usr/bin/env python3
"""
Compressed RX (receiver) with DB updates.
Kept original structure: 8kHz, Opus decode, silence trim, FLAC archive, START/END.
DB updates: last_activity on START, and total_records_sent/total_data_sent_bytes/transcription on save.
"""

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
import psycopg2

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
# DATABASE CONFIG & HELPERS
# ==========================
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"   # <-- change to your postgres password
}

def _db_execute(query, params=()):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] {str(e)}")

def db_update_activity(phone_number):
    _db_execute("""
        UPDATE human_users
        SET last_activity = %s
        WHERE phone_number = %s
    """, (datetime.now(), phone_number))

def db_update_end(phone_number, bytes_value, transcription_text=None):
    _db_execute("""
        UPDATE human_users
        SET total_records_sent = total_records_sent + 1,
            total_data_sent_bytes = total_data_sent_bytes + %s,
            transcription = %s,
            last_activity = %s
        WHERE phone_number = %s
    """, (bytes_value, transcription_text, datetime.now(), phone_number))

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
                # update DB activity for this receiver (my_number)
                try:
                    db_update_activity(self.my_number)
                except Exception as e:
                    print(f"[DB] activity update failed: {e}")
                return

            if message.startswith("END"):
                print("[CALL] Call ended by TX")
                call_active = False
                save_wav()
                # clear buffer after save (keeps behavior same)
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

    # METHOD 3: Silence trimming
    audio_data = trim_silence(audio_data)

    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.wav")

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)

    # METHOD 4: FLAC archive attempt
    flac_name = filename.replace(".wav", ".flac")
    try:
        subprocess.run(["flac", "-f", filename], check=False)
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

    # Update DB: increment counters and save a transcription placeholder
    try:
        db_update_end(my_number=receiver_number_for_db(), bytes_value=len(audio_data),
                      transcription_text="Recorded and saved")
    except Exception as e:
        print(f"[DB] end update failed: {e}")

# Helper to determine which DB record to update.
# We update the receiver's record (the my_number entered when starting RX).
def receiver_number_for_db():
    # This function returns the phone_number used when launched.
    # We store it at module-level when starting.
    return _RX_USER_NUMBER

# ==========================
if __name__ == "__main__":
    # store receiver DB id for use in save_wav
    _RX_USER_NUMBER = input("Enter your number: ")
    receiver_number = _RX_USER_NUMBER

    receiver = VoiceReceiver(receiver_number)

    while True:
        time.sleep(0.5)
