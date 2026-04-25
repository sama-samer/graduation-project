import whisper
import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import json
import paho.mqtt.client as mqtt
from datetime import datetime

SAMPLE_RATE         = 16000
CHANNELS            = 1
RECORDINGS_DIR      = "recordings"
TRANSCRIPTIONS_FILE = "transcriptions.json"
COMMANDS_FILE       = "commands.json"
WHISPER_MODEL       = "base"

# MQTT CONFIG
MQTT_BROKER   = "192.168.110.141"
MQTT_PORT     = 1884
MQTT_USERNAME = ""
MQTT_PASSWORD = ""

INTENT_MAP = {
    "OPEN": [
        "open", "start", "launch", "turn on", "activate", "enable", "begin", "run"
    ],
    "ANALYZE": [
        "analyze", "analyse", "read", "get", "fetch", "show", "check",
        "measure", "sensor", "reading", "data", "value", "report"
    ],
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



def ensure_file(filepath: str, default_content: str = ""):
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            f.write(default_content)



def record_audio(filename: str, duration: int = None) -> str:
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    filepath = os.path.join(RECORDINGS_DIR, filename)

    print("[*] Recording started...")

    if duration:
        audio_data = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32"
        )
        sd.wait()
    else:
        recorded_chunks = []

        def callback(indata, frames, time, status):
            recorded_chunks.append(indata.copy())

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype="float32", callback=callback):
            input("Press Enter to stop recording...\n")

        audio_data = np.concatenate(recorded_chunks, axis=0)

    sf.write(filepath, audio_data, SAMPLE_RATE)
    print(f"[+] Saved → {filepath}")
    return filepath


def analyze_audio(filepath: str) -> dict:
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(filepath)

    output = {
        "file": filepath,
        "language": result.get("language", "unknown"),
        "text": result["text"].strip(),
        "segments": [
            {
                "start": round(s["start"], 2),
                "end": round(s["end"], 2),
                "text": s["text"].strip()
            }
            for s in result.get("segments", [])
        ]
    }

    print(f"[+] Transcript: {output['text']}")
    return output


def detect_intent(text: str) -> str:
    lowered = text.lower()
    for intent, keywords in INTENT_MAP.items():
        if any(kw in lowered for kw in keywords):
            print(f"[+] Intent: {intent}")
            return intent
    return "UNKNOWN"


# ─────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────

def validate(text: str, intent: str) -> bool:
    if not text.strip():
        return False
    if intent == "UNKNOWN":
        return False
    if len(text.split()) < 2:
        return False
    return True


# ─────────────────────────────────────────────
# SAVE TRANSCRIPTION
# ─────────────────────────────────────────────

def save_transcription(transcript: dict, intent: str, valid: bool) -> dict:
    ensure_file(TRANSCRIPTIONS_FILE, "[]")

    with open(TRANSCRIPTIONS_FILE, "r") as f:
        try:
            records = json.load(f)
        except:
            records = []

    record = {
        "id": len(records) + 1,
        "timestamp": datetime.now().isoformat(),
        **transcript,
        "intent": intent,
        "valid": valid,
    }

    records.append(record)

    with open(TRANSCRIPTIONS_FILE, "w") as f:
        json.dump(records, f, indent=2)

    return record


# ─────────────────────────────────────────────
# SAVE COMMAND
# ─────────────────────────────────────────────

def save_command(record: dict) -> dict | None:
    ensure_file(COMMANDS_FILE, "[]")

    with open(COMMANDS_FILE, "r") as f:
        try:
            commands = json.load(f)
        except:
            commands = []

    if not record["valid"]:
        return None

    intent = record["intent"]
    payload = COMMAND_DISPATCH.get(intent)

    if not payload:
        return None

    command = {
        "id": len(commands) + 1,
        "timestamp": record["timestamp"],
        "transcription_id": record["id"],
        "intent": intent,
        "esp_payload": payload,
        "mqtt_topic": "esp/commands",
        "dispatched": False,
    }

    commands.append(command)

    with open(COMMANDS_FILE, "w") as f:
        json.dump(commands, f, indent=2)

    return command


def dispatch_last_command() -> bool:
    ensure_file(COMMANDS_FILE, "[]")

    with open(COMMANDS_FILE, "r") as f:
        try:
            commands = json.load(f)
        except:
            commands = []

    if not commands:
        print("[!] No commands found")
        return False

    command = commands[-1]

    if command.get("dispatched"):
        print(f"[!] Command #{command['id']} already dispatched")
        return False

    payload = json.dumps({
        "command_id": command["id"],
        "timestamp": command["timestamp"],
        **command["esp_payload"]
    })

    try:
        client = mqtt.Client(client_id=f"voice-{command['id']}")

        if MQTT_USERNAME:
            client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        client.connect(MQTT_BROKER, MQTT_PORT, 10)

        result = client.publish(command["mqtt_topic"], payload, qos=1)
        result.wait_for_publish()

        client.disconnect()

        print(f"[+] Sent → {command['mqtt_topic']}")
        print(payload)

        commands[-1]["dispatched"] = True

        with open(COMMANDS_FILE, "w") as f:
            json.dump(commands, f, indent=2)

        return True

    except Exception as e:
        print(f"[!] MQTT Error: {e}")
        return False


def run_dispatch_only():
    success = dispatch_last_command()
    print("Success" if success else "Failed")


if __name__ == "__main__":
    os.makedirs(RECORDINGS_DIR, exist_ok=True)

    existing = [f for f in os.listdir(RECORDINGS_DIR) if f.endswith(".wav")]
    filename = f"recording_{len(existing)+1}.wav"

    filepath   = record_audio(filename)
    transcript = analyze_audio(filepath)
    intent     = detect_intent(transcript["text"])
    valid      = validate(transcript["text"], intent)

    record  = save_transcription(transcript, intent, valid)
    command = save_command(record)
    sent    = dispatch_last_command()

    print("\n──── RESULT ────")
    print(f"Text     : {record['text']}")
    print(f"Intent   : {record['intent']}")
    print(f"Valid    : {record['valid']}")
    print(f"Sent     : {sent}")