#!/usr/bin/env python3
"""
Receiver: Record MQTT voice stream
- Prints recording time
- Prints recorded size (bytes + MB)
- Sends ACK to TX
- Saves WAV file
"""

import argparse
import struct
import threading
import time
import wave
import paho.mqtt.client as mqtt

# ==========================
# CONFIGURATION
# ==========================
SAMPLE_RATE = 32000
CHANNELS = 1
BIT_DEPTH = 16
BYTES_PER_SAMPLE = BIT_DEPTH // 8
CHUNK = 512

VER = 1
HEADER_STRUCT = struct.Struct("!BI")
HEADER_SIZE = HEADER_STRUCT.size

# ==========================
# GLOBAL STATE
# ==========================
received_frames = []
received_lock = threading.Lock()

current_sender = None
ack_sent = False
record_start_time = None
total_bytes_received = 0

# ==========================
# MQTT RECEIVER CLASS
# ==========================
class VoiceReceiver:
    def __init__(self, broker, port, my_number):
        self.my_number = my_number
        self.signal_topic = f"pbx/voice/signal/{my_number}"
        self.live_topic = f"pbx/voice/live/{my_number}"

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.connect(broker, port, 60)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] Connected (rc={rc})")
        client.subscribe(self.signal_topic)
        client.subscribe(self.live_topic)
        print(f"[MQTT] Listening on {self.signal_topic}")
        print(f"[MQTT] Listening on {self.live_topic}")

    def on_message(self, client, userdata, msg):
        global current_sender, ack_sent
        global record_start_time, total_bytes_received

        # ===== START SIGNAL =====
        if msg.topic == self.signal_topic:
            try:
                text = msg.payload.decode()
                if text.startswith("START:"):
                    current_sender = text.split(":")[1]
                    ack_sent = False
                    record_start_time = None
                    total_bytes_received = 0

                    print("\n================================")
                    print(f"[CALL] Voice incoming from TX {current_sender}")
                    print("[CALL] Waiting for audio...")
                    print("================================\n")
            except:
                pass
            return

        # ===== AUDIO PACKET =====
        if msg.topic == self.live_topic:
            if len(msg.payload) < HEADER_SIZE:
                return

            try:
                ver, seq = HEADER_STRUCT.unpack(msg.payload[:HEADER_SIZE])
                if ver != VER:
                    return

                pcm_bytes = msg.payload[HEADER_SIZE:]

                with received_lock:
                    received_frames.append(pcm_bytes)

                total_bytes_received += len(pcm_bytes)

                # First packet detection
                if record_start_time is None:
                    record_start_time = time.time()
                    print(f"[RX] Voice stream started from TX {current_sender}")

                    # Send ACK
                    if current_sender and not ack_sent:
                        ack_topic = f"pbx/voice/ack/{current_sender}"
                        ack_payload = f"RECEIVING:{self.my_number}"
                        client.publish(ack_topic, ack_payload.encode())
                        print(f"[ACK] Sent to TX {current_sender}")
                        ack_sent = True

            except:
                pass


# ==========================
# LIVE MONITOR THREAD
# ==========================
def monitor_recording():
    global record_start_time, total_bytes_received

    while True:
        time.sleep(1)

        if record_start_time:
            duration = time.time() - record_start_time
            size_mb = total_bytes_received / (1024 * 1024)

            print(f"[LIVE] Duration: {duration:.1f} sec | "
                  f"Size: {total_bytes_received} bytes "
                  f"({size_mb:.2f} MB)")


# ==========================
# SAVE WAV FILE
# ==========================
def save_wav(filename):
    global record_start_time, total_bytes_received

    with received_lock:
        audio_data = b''.join(received_frames)

    if not audio_data:
        print("[SAVE] No audio recorded.")
        return

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(BYTES_PER_SAMPLE)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)

    duration_sec = len(audio_data) / (SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE)
    size_mb = len(audio_data) / (1024 * 1024)

    print("\n================================")
    print("[SAVE] Recording Finished")
    print(f"[SAVE] File: {filename}")
    print(f"[SAVE] Duration: {duration_sec:.2f} sec")
    print(f"[SAVE] Size: {len(audio_data)} bytes ({size_mb:.2f} MB)")
    print("================================")


# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", required=True)
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--listen", required=True)
    parser.add_argument("--outfile", default=None)
    args = parser.parse_args()

    outfile = args.outfile or f"rx_{args.listen}.wav"

    receiver = VoiceReceiver(args.broker, args.port, args.listen)

    # Start monitor thread
    monitor_thread = threading.Thread(target=monitor_recording, daemon=True)
    monitor_thread.start()

    print("\n[INFO] Receiver ready (record mode)")
    print("[INFO] Press Ctrl+C to stop and save\n")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping receiver...")
        save_wav(outfile)
