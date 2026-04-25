#!/usr/bin/env python3
"""
Compressed TX (sender) with DB updates.
Kept original structure: 8kHz, Opus, START/END signal, VBR, stats.
DB updates: last_login, last_activity (throttled), total_records_sent, total_data_sent_bytes, destination_id.
"""

import threading
import struct
import time
import socket
import numpy as np
import sounddevice as sd
import paho.mqtt.client as mqtt
import opuslib
import psycopg2
from datetime import datetime

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
    """Simple helper to execute a single query safely."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        # Do not raise — logging only to avoid stopping TX
        print(f"[DB ERROR] {_safe_str(e)}")

def _safe_str(x):
    try:
        return str(x)
    except:
        return "<unprintable>"

def db_update_start(phone_number, destination_id):
    _db_execute("""
        UPDATE human_users
        SET last_login = %s,
            last_activity = %s,
            destination_id = %s
        WHERE phone_number = %s
    """, (datetime.now(), datetime.now(), destination_id, phone_number))

def db_update_activity(phone_number):
    _db_execute("""
        UPDATE human_users
        SET last_activity = %s
        WHERE phone_number = %s
    """, (datetime.now(), phone_number))

def db_update_end(phone_number, bytes_sent):
    _db_execute("""
        UPDATE human_users
        SET total_records_sent = total_records_sent + 1,
            total_data_sent_bytes = total_data_sent_bytes + %s,
            last_activity = %s
        WHERE phone_number = %s
    """, (bytes_sent, datetime.now(), phone_number))

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
    # send START and update DB (destination_id stored)
    sender.publish_start(dest)
    try:
        db_update_start(my_number, dest)
    except Exception as e:
        print(f"[DB] start update failed: {_safe_str(e)}")

    sender.received_ack_event.wait(3)

    tx_seq = 0
    total_bytes_sent = 0
    start_time = time.time()
    lock = threading.Lock()

    # For throttled activity updates
    last_activity_update = 0.0
    ACTIVITY_UPDATE_INTERVAL = 1.0  # seconds

    def callback(indata, frames, time_info, status):
        nonlocal tx_seq, total_bytes_sent, last_activity_update
        pcm = indata.astype(np.int16).tobytes()
        compressed = encoder.encode(pcm, CHUNK)

        with lock:
            seq = tx_seq
            tx_seq = (tx_seq + 1) & 0xFFFFFFFF

        sender.publish_audio(dest, seq, compressed)
        total_bytes_sent += len(compressed)

        # Throttled DB activity update (once per second)
        now = time.time()
        if now - last_activity_update >= ACTIVITY_UPDATE_INTERVAL:
            try:
                db_update_activity(my_number)
            except Exception as e:
                print(f"[DB] activity update failed: {_safe_str(e)}")
            last_activity_update = now

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
        # send END signal
        sender.publish_end(dest)

        # update DB with totals
        try:
            db_update_end(my_number, total_bytes_sent)
        except Exception as e:
            print(f"[DB] end update failed: {_safe_str(e)}")

        duration = time.time() - start_time
        size_mb = total_bytes_sent / (1024 * 1024)

        print("\n================================")
        print("[TX] Recording Finished")
        print(f"[TX] Duration: {duration:.2f} sec")
        print(f"[TX] Size: {total_bytes_sent} bytes ({size_mb:.2f} MB)")
        print("================================")

        sender.client.loop_stop()
        sender.client.disconnect()

# ==========================
if __name__ == "__main__":
    my_number = input("Enter your number: ")
    destination = input("Enter destination number: ")
    run_sender(my_number, destination)
