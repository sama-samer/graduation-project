#!/usr/bin/env python3
"""
RX: receiver with heartbeat publisher and graceful close notification.
Preserves all original features: Opus decode, silence trim, FLAC archive, WAV save,
saving WAV bytes into human_users.last_record (BYTEA), updating device_mac.
On graceful shutdown, RX notifies TX by publishing RECEIVER_CLOSING on ACK topic.
"""
import struct
import threading
import time
import wave
import socket
import uuid
import numpy as np
import subprocess
from datetime import datetime
import paho.mqtt.client as mqtt
import opuslib
import psycopg2
from psycopg2 import Binary

# -----------------------
# CONFIG
# -----------------------
BROKER = socket.gethostbyname(socket.gethostname())
PORT = 1884

SAMPLE_RATE = 8000
CHANNELS = 1
CHUNK = int(SAMPLE_RATE * 20 / 1000)

VER = 1
HEADER_STRUCT = struct.Struct("!BI")
HEADER_SIZE = HEADER_STRUCT.size

decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)

# Shared buffers/state
received_frames = []
received_lock = threading.Lock()

call_active = False
current_sender = None
last_rx_seq = -1
last_rx_seq_lock = threading.Lock()
total_bytes_received = 0

# -----------------------
# DB CONFIG
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"   # <<-- set your postgres password
}

def _safe_str(x):
    try:
        return str(x)
    except:
        return "<unprintable>"

def _db_execute(query, params=()):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("[DB ERROR]", _safe_str(e))

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

def db_write_last_record(phone_number, wav_bytes):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            UPDATE human_users
            SET last_record = %s, last_activity = %s
            WHERE phone_number = %s
        """, (Binary(wav_bytes), datetime.now(), phone_number))
        conn.commit()
        cur.close()
        conn.close()
        print("[DB] last_record updated for", phone_number)
    except Exception as e:
        print("[DB ERROR] write_last_record:", _safe_str(e))

# -----------------------
# device_mac update by human_users.device_ip
def get_real_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = socket.gethostbyname(socket.gethostname())
    finally:
        s.close()
    return ip

def get_local_mac():
    node = uuid.getnode()
    return ':'.join(f"{(node >> ele) & 0xff:02x}" for ele in range(40, -1, -8))

def db_update_human_device_mac_by_ip(ip_address, mac_str):
    try:
        _db_execute("""
            UPDATE human_users
            SET device_mac = %s, last_activity = %s
            WHERE device_ip::text = %s
        """, (mac_str, datetime.now(), str(ip_address)))
        print(f"[DB] attempted to update human_users.device_mac for ip={ip_address}")
    except Exception as e:
        print("[DB ERROR] db_update_human_device_mac_by_ip:", _safe_str(e))

# startup MAC update
try:
    local_ip = get_real_ip()
    local_mac = get_local_mac()
    print(f"[SYS] Local IP={local_ip}, MAC={local_mac}")
    db_update_human_device_mac_by_ip(local_ip, local_mac)
except Exception as e:
    print("[SYS] device MAC update skipped:", _safe_str(e))

# -----------------------
class VoiceReceiver:
    def __init__(self, my_number):
        self.my_number = my_number
        self.signal_topic = f"pbx/voice/signal/{my_number}"
        self.live_topic = f"pbx/voice/live/{my_number}"
        self.client = None
        # try to use new callback API if available
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except Exception:
            self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.connect(BROKER, PORT)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, rc, properties=None):
        try:
            client.subscribe(self.signal_topic)
            client.subscribe(self.live_topic)
        except Exception:
            pass
        print(f"[RX] Listening on {BROKER}:{PORT}")

    def on_message(self, client, userdata, msg):
        global call_active, current_sender, last_rx_seq, total_bytes_received

        # SIGNAL topic handling
        if msg.topic == self.signal_topic:
            try:
                text = msg.payload.decode(errors="ignore")
            except Exception:
                text = str(msg.payload)

            if text.startswith("START:"):
                sender_num = text.split(":", 1)[1]
                if call_active:
                    print(f"[SIGNAL] START from {sender_num} ignored (busy with {current_sender})")
                    return

                # accept call
                current_sender = sender_num
                call_active = True
                last_rx_seq = -1
                total_bytes_received = 0
                with received_lock:
                    received_frames.clear()

                # send ACK
                try:
                    client.publish(f"pbx/voice/ack/{current_sender}", "RECEIVING")
                except Exception:
                    pass
                print(f"[CALL] START from {current_sender} -> ACK sent")
                try:
                    db_update_activity(self.my_number)
                except Exception:
                    pass

                # start heartbeat thread
                hb_t = threading.Thread(target=self._hb_publisher, args=(current_sender,), daemon=True)
                hb_t.start()
                return

            if text.startswith("END:"):
                sender_num = text.split(":", 1)[1]
                if call_active and sender_num == current_sender:
                    print(f"[CALL] END received from {sender_num}")
                    call_active = False
                    save_wav_and_db(sender_num)
                    current_sender = None
                else:
                    print(f"[SIGNAL] END from {sender_num} ignored (no matching call)")
                return

        # LIVE audio packets
        if msg.topic == self.live_topic and call_active:
            if len(msg.payload) < HEADER_SIZE:
                return
            try:
                ver, seq = HEADER_STRUCT.unpack(msg.payload[:HEADER_SIZE])
            except Exception:
                return
            if ver != VER:
                return

            with last_rx_seq_lock:
                if seq <= last_rx_seq:
                    return
                last_rx_seq = seq

            compressed = msg.payload[HEADER_SIZE:]
            try:
                decoded = decoder.decode(compressed, CHUNK)
            except Exception:
                return

            with received_lock:
                received_frames.append(decoded)
            total_bytes_received += len(decoded)

    def _hb_publisher(self, sender_num):
        """Publish heartbeat to pbx/voice/hb/<sender_num> while call active."""
        hb_topic = f"pbx/voice/hb/{sender_num}"
        while call_active and current_sender == sender_num:
            try:
                self.client.publish(hb_topic, "HB")
            except Exception:
                pass
            time.sleep(1.0)
        # when call is ending (graceful), notify sender via ACK topic
        try:
            self.client.publish(f"pbx/voice/ack/{sender_num}", "RECEIVER_CLOSING")
        except Exception:
            pass

# -----------------------
def trim_silence(audio_bytes, threshold=500):
    audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
    mask = np.abs(audio_np) > threshold
    if not np.any(mask):
        return audio_bytes
    first = np.argmax(mask)
    last = len(audio_np) - np.argmax(mask[::-1])
    trimmed = audio_np[first:last]
    return trimmed.astype(np.int16).tobytes()

# -----------------------
def save_wav_and_db(sender_number_for_db):
    with received_lock:
        audio_data = b''.join(received_frames)

    if not audio_data:
        print("[SAVE] No audio to save.")
        # still update record count? probably not
        return

    # silence trim
    audio_data = trim_silence(audio_data)

    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.wav")
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)

    # FLAC archive (optional)
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

    # DB update
    try:
        db_update_end(phone_number=sender_number_for_db, bytes_value=len(audio_data),
                      transcription_text="Recorded and saved")
    except Exception as e:
        print("[DB] end update failed:", _safe_str(e))

    # Save WAV bytes into human_users.last_record (BYTEA)
    try:
        db_write_last_record(phone_number=sender_number_for_db, wav_bytes=audio_data)
    except Exception as e:
        print("[DB] saving WAV bytes failed:", _safe_str(e))

# -----------------------
if __name__ == "__main__":
    RX_NUMBER = input("Enter your number: ")
    receiver = VoiceReceiver(RX_NUMBER)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        # if active call, finalize it and notify sender
        if call_active and current_sender:
            print("[RX] Stopping: finishing active call")
            # publish RECEIVER_CLOSING to tell TX to stop (ACK topic)
            try:
                receiver.client.publish(f"pbx/voice/ack/{current_sender}", "RECEIVER_CLOSING")
            except Exception:
                pass
            save_wav_and_db(current_sender)
        print("[RX] Exiting.")
        try:
            receiver.client.loop_stop()
            receiver.client.disconnect()
        except Exception:
            pass
