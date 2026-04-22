import whisper 
import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import json
import paho.mqtt.client as mqtt
from datetime import datetime

# --- CONFIG ---
SAMPLE_RATE = 16000
CHANNELS = 1
RECORDINGS_DIR = "recordings"
WHISPER_MODEL = "base"

# --- MQTT CONFIG ---
MQTT_BROKER = "172.20.10.2"
MQTT_PORT = 1884
MQTT_TOPIC = "test"

# --- INTENT MAP ---
INTENT_MAP = {
    "OPEN": ["open", "start", "launch", "turn on", "activate", "run"],
    "ANALYZE": ["analyze", "read", "get", "check", "data"]
}

COMMAND_DISPATCH = {
    "OPEN": {
        "action": "OPEN",
        "target": "system",
        "description": "Initialize and open the system"
    },
    "ANALYZE": {
        "action": "READ_SENSORS",
        "target": "sensors",
        "description": "Read and return all sensor values"
    },
}

# --- MQTT CLIENT ---
client = mqtt.Client()

def connect_mqtt():
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 10)
        client.loop_start()
        print("[+] Connected to MQTT broker")
    except Exception as e:
        print(f"[!] MQTT error: {e}")

def publish(payload: dict):
    try:
        message = json.dumps(payload)
        client.publish(MQTT_TOPIC, message, qos=1).wait_for_publish()
        print(f"[+] Sent to MQTT topic: {MQTT_TOPIC}")
    except Exception as e:
        print(f"[!] Publish error: {e}")

# --- RECORD ---
def record_audio(filename: str):
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    filepath = os.path.join(RECORDINGS_DIR, filename)

    print("[*] Recording... Press Enter to stop")

    chunks = []

    def callback(indata, frames, time, status):
        chunks.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        dtype="float32", callback=callback):
        input()

    audio = np.concatenate(chunks, axis=0)
    sf.write(filepath, audio, SAMPLE_RATE)

    print(f"[+] Saved → {filepath}")
    return filepath

# --- TRANSCRIBE ---
def analyze_audio(filepath: str):
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(filepath, language="en")  # 🔥 force English

    return result["text"].strip()

# --- INTENT ---
def detect_intent(text: str) -> str:
    text = text.lower()
    for intent, keywords in INTENT_MAP.items():
        if any(k in text for k in keywords):
            return intent
    return "UNKNOWN"

# --- VALIDATION ---
def validate(text: str, intent: str) -> bool:
    return bool(text.strip()) and intent != "UNKNOWN" and len(text.split()) > 1

# --- MAIN ---
def main():
    connect_mqtt()

    filename = "recording.wav"
    filepath = record_audio(filename)

    text = analyze_audio(filepath)
    intent = detect_intent(text)
    valid = validate(text, intent)

    print("\n──── RESULT ────")
    print(f"Text     : {text}")
    print(f"Intent   : {intent}")
    print(f"Valid    : {valid}")

    if not valid:
        print("[!] Invalid command → NOT sent")
        return

    payload = {
        "id": 0,
        "timestamp": datetime.now().isoformat(),
        "text": text,
        "intent": intent,
        "valid": valid,
        "esp_payload": COMMAND_DISPATCH[intent]
    }

    publish(payload)

    client.loop_stop()
    client.disconnect()

# --- RUN ---
if __name__ == "__main__":
    main()