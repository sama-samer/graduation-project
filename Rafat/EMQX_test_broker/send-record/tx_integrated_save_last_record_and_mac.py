#!/usr/bin/env python3
"""
TX: sender with reliable DB accounting and RX-close handling.
Added: live printing of sent compressed bytes & bitrate every second.

Preserves all original features:
- 8 kHz Opus VBR streaming
- START/ACK/END signaling (wait for ACK before mic)
- LWT for unexpected disconnects
- Periodic DB flush of compressed bytes -> total_data_sent_bytes
- Heartbeat watchdog / RX-close handling
- DB updates and device_mac update
"""
import threading
import struct
import time
import socket
import uuid
import numpy as np
import sounddevice as sd
import paho.mqtt.client as mqtt
import opuslib
import psycopg2
from datetime import datetime

# -----------------------
# CONFIG
# -----------------------
BROKER = socket.gethostbyname(socket.gethostname())
PORT = 1884

SAMPLE_RATE = 8000
CHANNELS = 1
CHUNK = int(SAMPLE_RATE * 20 / 1000)
BITRATE = 16000

VER = 1
HEADER_STRUCT = struct.Struct("!BI")

# Heartbeat/watchdog
HEARTBEAT_TOPIC_FMT = "pbx/voice/hb/{}"
HEARTBEAT_TIMEOUT = 6.0  # seconds without hb -> consider RX gone

# DB flush
DB_FLUSH_INTERVAL = 2.0   # seconds
DB_FLUSH_THRESHOLD = 8*1024  # bytes

# -----------------------
# Opus encoder
encoder = opuslib.Encoder(SAMPLE_RATE, CHANNELS, opuslib.APPLICATION_VOIP)
encoder.bitrate = BITRATE
encoder.vbr = True

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

def db_update_start(phone_number, destination_id):
    _db_execute("""
        UPDATE human_users
        SET last_login = %s, last_activity = %s, destination_id = %s
        WHERE phone_number = %s
    """, (datetime.now(), datetime.now(), destination_id, phone_number))

def db_update_activity(phone_number):
    _db_execute("""
        UPDATE human_users
        SET last_activity = %s
        WHERE phone_number = %s
    """, (datetime.now(), phone_number))

def db_increment_data_sent_bytes(phone_number, bytes_amount):
    if bytes_amount <= 0:
        return
    _db_execute("""
        UPDATE human_users
        SET total_data_sent_bytes = total_data_sent_bytes + %s,
            last_activity = %s
        WHERE phone_number = %s
    """, (bytes_amount, datetime.now(), phone_number))

def db_increment_record_count(phone_number):
    _db_execute("""
        UPDATE human_users
        SET total_records_sent = total_records_sent + 1,
            last_activity = %s
        WHERE phone_number = %s
    """, (datetime.now(), phone_number))

# -----------------------
# device MAC update (human_users.device_mac by device_ip)
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

# Update device_mac on startup (best-effort)
try:
    local_ip = get_real_ip()
    local_mac = get_local_mac()
    print(f"[SYS] Local IP={local_ip}, MAC={local_mac}")
    db_update_human_device_mac_by_ip(local_ip, local_mac)
except Exception as e:
    print("[SYS] device MAC update skipped:", _safe_str(e))

# -----------------------
class MqttVoiceSender:
    def __init__(self, my_number):
        # use newer callback API if available
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except Exception:
            self.client = mqtt.Client()
        self.my_number = my_number
        self.ack_topic = f"pbx/voice/ack/{self.my_number}"
        self.hb_topic = HEARTBEAT_TOPIC_FMT.format(self.my_number)
        self.received_ack_event = threading.Event()
        self._last_hb_time = None
        self._hb_lock = threading.Lock()
        self._bytes_lock = threading.Lock()
        self._bytes_since_flush = 0
        self._connected = False

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def set_lwt_and_connect(self, dest):
        # set LWT to notify remote that TX died unexpectedly (END:<tx>)
        try:
            self.client.will_set(f"pbx/voice/signal/{dest}",
                                 payload=f"END:{self.my_number}", qos=1, retain=False)
        except Exception:
            pass
        self.client.connect(BROKER, PORT)
        self.client.loop_start()
        self._connected = True

    # paho callback signature v2-compatible (works even if library uses v1)
    def on_connect(self, client, userdata, flags, rc, properties=None):
        try:
            client.subscribe(self.ack_topic)
            client.subscribe(self.hb_topic)
        except Exception:
            pass

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = None
        try:
            payload = msg.payload.decode(errors="ignore")
        except Exception:
            payload = str(msg.payload)

        if topic == self.ack_topic:
            print("[ACK]", payload)
            if isinstance(payload, str) and payload.startswith("RECEIVING"):
                self.received_ack_event.set()
            if isinstance(payload, str) and payload.startswith("RECEIVER_CLOSING"):
                print("[INFO] RECEIVER_CLOSING received via ACK.")
                with self._hb_lock:
                    self._last_hb_time = 0.0

        elif topic == self.hb_topic:
            # heartbeat from receiver
            with self._hb_lock:
                self._last_hb_time = time.time()

    def publish_start(self, dest):
        try:
            self.client.publish(f"pbx/voice/signal/{dest}", f"START:{self.my_number}")
        except Exception:
            pass

    def publish_end(self, dest):
        try:
            self.client.publish(f"pbx/voice/signal/{dest}", f"END:{self.my_number}")
        except Exception:
            pass

    def publish_audio(self, dest, seq, compressed_bytes):
        header = HEADER_STRUCT.pack(VER, seq)
        try:
            self.client.publish(f"pbx/voice/live/{dest}", header + compressed_bytes)
        except Exception:
            pass
        with self._bytes_lock:
            self._bytes_since_flush += len(compressed_bytes)

    def pop_bytes_since_flush(self):
        with self._bytes_lock:
            n = self._bytes_since_flush
            self._bytes_since_flush = 0
            return n

    def last_hb_age(self):
        with self._hb_lock:
            if self._last_hb_time is None:
                return float('inf')
            return time.time() - self._last_hb_time

# -----------------------
def run_sender(my_number, dest):
    sender = MqttVoiceSender(my_number)
    sender.set_lwt_and_connect(dest)

    # send START and update DB
    sender.publish_start(dest)
    try:
        db_update_start(my_number, dest)
    except Exception as e:
        print("[DB] start update failed:", _safe_str(e))

    # wait for ACK (resend START every 1s)
    print("[INFO] Waiting for receiver ACK before starting audio (resend every 1s)...")
    try:
        while not sender.received_ack_event.is_set():
            sender.publish_start(dest)
            sender.received_ack_event.wait(1.0)
    except KeyboardInterrupt:
        print("\n[TX] Aborted before ACK; sending END and exiting.")
        try:
            sender.publish_end(dest)
        except Exception:
            pass
        if sender._connected:
            sender.client.loop_stop()
            sender.client.disconnect()
        return

    print("[INFO] ACK received. Starting audio capture & streaming.")

    # DB flush worker (periodically flush bytes to DB)
    stop_event = threading.Event()
    def db_flush_worker():
        while not stop_event.is_set():
            time.sleep(DB_FLUSH_INTERVAL)
            try:
                n = sender.pop_bytes_since_flush()
                if n > 0:
                    db_increment_data_sent_bytes(my_number, n)
            except Exception as e:
                print("[DB] flush worker error:", _safe_str(e))
    flush_thread = threading.Thread(target=db_flush_worker, daemon=True)
    flush_thread.start()

    # streaming variables
    tx_seq = 0
    total_bytes_sent_local = 0
    total_bytes_lock = threading.Lock()
    start_time = time.time()
    last_activity_update = 0.0
    ACTIVITY_UPDATE_INTERVAL = 1.0

    # for live printing
    last_print_time = time.time()
    last_print_bytes = 0

    # audio callback
    def audio_callback(indata, frames, time_info, status):
        nonlocal tx_seq, total_bytes_sent_local, last_activity_update
        try:
            pcm = indata.astype(np.int16).tobytes()
            compressed = encoder.encode(pcm, CHUNK)
            seq = tx_seq
            tx_seq = (tx_seq + 1) & 0xFFFFFFFF
            sender.publish_audio(dest, seq, compressed)
            with total_bytes_lock:
                total_bytes_sent_local += len(compressed)

            now = time.time()
            if now - last_activity_update >= ACTIVITY_UPDATE_INTERVAL:
                try:
                    db_update_activity(my_number)
                except Exception:
                    pass
                last_activity_update = now
        except Exception as e:
            print("[TX CALLBACK ERROR]", _safe_str(e))

    # start stream
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype="int16", blocksize=CHUNK, callback=audio_callback)
    stream.start()

    # initialize last heartbeat now (we expect hb soon)
    with sender._hb_lock:
        sender._last_hb_time = time.time()

    try:
        while True:
            time.sleep(0.5)
            # print live sending stats every 1s
            now = time.time()
            if now - last_print_time >= 1.0:
                with total_bytes_lock:
                    total = total_bytes_sent_local
                interval_bytes = total - last_print_bytes
                interval_bps = (interval_bytes * 8) / (now - last_print_time) if (now - last_print_time) > 0 else 0
                avg_bps = (total * 8) / (now - start_time) if (now - start_time) > 0 else 0
                print(f"[TX STATS] total={total} bytes | interval={interval_bytes} B | "
                      f"instant={interval_bps:.0f} bps | avg={avg_bps:.0f} bps")
                last_print_time = now
                last_print_bytes = total

            # Watchdog: check last heartbeat age
            age = sender.last_hb_age()
            if age > HEARTBEAT_TIMEOUT:
                print(f"[WATCHDOG] No heartbeat for {age:.1f}s (> {HEARTBEAT_TIMEOUT}s). Stopping stream.")
                break
    except KeyboardInterrupt:
        print("[TX] KeyboardInterrupt — stopping.")
    finally:
        # stop and close stream
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass

        # flush remaining bytes to DB
        try:
            leftover = sender.pop_bytes_since_flush()
            if leftover > 0:
                db_increment_data_sent_bytes(my_number, leftover)
        except Exception as e:
            print("[DB] final flush failed:", _safe_str(e))

        # increment record count
        try:
            db_increment_record_count(my_number)
        except Exception as e:
            print("[DB] final record increment failed:", _safe_str(e))

        duration = time.time() - start_time
        with total_bytes_lock:
            total = total_bytes_sent_local

        print("\n================================")
        print("[TX] Recording Finished")
        print(f"[TX] Duration: {duration:.2f} sec")
        print(f"[TX] Total compressed bytes sent: {total} bytes ({total/1024:.2f} KB)")
        print("================================")

        stop_event.set()
        flush_thread.join(timeout=1.0)

        if sender._connected:
            try:
                sender.client.loop_stop()
                sender.client.disconnect()
            except Exception:
                pass

# -----------------------
if __name__ == "__main__":
    my_number = input("Enter your number: ")
    destination = input("Enter destination number: ")
    run_sender(my_number, destination)
