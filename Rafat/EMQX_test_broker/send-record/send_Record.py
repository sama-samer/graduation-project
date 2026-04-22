#!/usr/bin/env python3
"""
sender.py
Capture microphone audio and publish PCM packets over MQTT.

Usage:
    python sender.py --broker 172.20.10.2 --port 1884 --from 100 --to 101
"""
import argparse
import threading
import struct
import time
import numpy as np
import sounddevice as sd
import paho.mqtt.client as mqtt

# -----------------------
# CONFIG (easy to change)
# -----------------------
SAMPLE_RATE = 32000       # Hz
CHANNELS = 1
DTYPE = 'int16'           # numpy dtype used for PCM
CHUNK = 512               # frames per packet (tune for latency)
AMPLIFY_TX = 10.0         # multiply microphone level (clamp applied)
VER = 1
HEADER_STRUCT = struct.Struct("!BI")  # VER:uint8, SEQ:uint32

# -----------------------
# MQTT helper (simple wrapper)
# -----------------------
class MqttVoiceSender:
    def __init__(self, broker, port, topic_send):
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.connect(broker, port, 60)
        self.thread = threading.Thread(target=self.client.loop_forever, daemon=True)
        self.thread.start()
        self.topic_send = topic_send

    def on_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] Connected (rc={rc})")

    def publish_packet(self, seq: int, pcm_bytes: bytes):
        header = HEADER_STRUCT.pack(VER, seq)
        packet = header + pcm_bytes
        # qos=0 for lowest latency; change to 1 if you need reliability
        self.client.publish(self.topic_send, packet, qos=0)

# -----------------------
# Audio capture -> MQTT
# -----------------------
def run_sender(broker, port, topic_send):
    sender = MqttVoiceSender(broker, port, topic_send)
    tx_seq = 0
    tx_seq_lock = threading.Lock()

    def audio_callback(indata, frames, time_info, status):
        nonlocal tx_seq
        # indata is shape (frames, channels) and dtype matching DTYPE
        try:
            data = indata.copy().astype(np.float32) * AMPLIFY_TX
            # clip and convert back to int16
            np.clip(data, -32768, 32767, out=data)
            pcm = data.astype(np.int16)
            pcm_bytes = pcm.tobytes()

            with tx_seq_lock:
                seq = tx_seq
                tx_seq = (tx_seq + 1) & 0xFFFFFFFF

            sender.publish_packet(seq, pcm_bytes)
        except Exception as e:
            # keep callback lightweight: print minimally
            print("[TX callback error]", e)

    print(f"[INFO] Starting capture: {SAMPLE_RATE}Hz, chunk={CHUNK}, dtype={DTYPE}")
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        dtype=DTYPE, blocksize=CHUNK,
                        callback=audio_callback, latency='low'):
        print(f"[INFO] Sending to topic: {topic_send}. Ctrl+C to stop.")
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("[INFO] Sender stopped.")

# -----------------------
# CLI
# -----------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", required=True)
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--from", dest="src", required=False)
    parser.add_argument("--to", dest="dst", required=True)
    args = parser.parse_args()

    TOPIC_SEND = f"pbx/voice/live/{args.dst}"
    run_sender(args.broker, args.port, TOPIC_SEND)
