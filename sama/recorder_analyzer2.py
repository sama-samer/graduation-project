import whisper
import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import json
import paho.mqtt.client as mqtt
from datetime import datetime

# --- CONFIG ---
SAMPLE_RATE         = 16000
CHANNELS            = 1
RECORDINGS_DIR      = "recordings"
TRANSCRIPTIONS_FILE = "transcriptions.json"
COMMANDS_FILE       = "commands.json"
WHISPER_MODEL       = "base"   # tiny | base | small | medium | large

# --- EMQX BROKER CONFIG (NanoMQ running locally) ---
MQTT_BROKER   = "localhost"
MQTT_PORT     = 1883
MQTT_USERNAME = ""             # leave empty if auth not enabled
MQTT_PASSWORD = ""             # leave empty if auth not enabled
MQTT_TOPIC    = "esp/commands" # ESP subscribes to this topic

# --- INTENT KEYWORDS ---
INTENT_MAP = {
    "OPEN": [
        "open", "start", "launch", "turn on", "activate", "enable", "begin", "run"
    ],
    "ANALYZE": [
        "analyze", "analyse", "read", "get", "fetch", "show", "check",
        "measure", "sensor", "reading", "data", "value", "report"
    ],
}

# --- COMMAND DISPATCH TABLE ---
# Intent → exact JSON payload the ESP will receive
COMMAND_DISPATCH = {
    "OPEN": {
        "action":      "OPEN",
        "target":      "system",
        "description": "Initialize and open the system"
    },
    "ANALYZE": {
        "action":      "READ_SENSORS",
        "target":      "sensors",
        "description": "Read and return all sensor values"
    },
}


# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────

def ensure_file(filepath: str, default_content: str = ""):
    """Create the file (and parent dirs) if it doesn't exist."""
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            f.write(default_content)
        print(f"[+] File created → {filepath}")


# ─────────────────────────────────────────────
# STEP 1 — RECORD
# ─────────────────────────────────────────────

def record_audio(filename: str, duration: int = None) -> str:
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    filepath = os.path.join(RECORDINGS_DIR, filename)
    ensure_file(filepath)
    print("[*] Recording started...")

    if duration:
        audio_data = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32"
        )
        sd.wait()
        print(f"[*] Recording stopped after {duration}s.")
    else:
        recorded_chunks = []

        def callback(indata, frames, time, status):
            recorded_chunks.append(indata.copy())

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype="float32", callback=callback):
            input("    Press Enter to stop recording...\n")

        audio_data = np.concatenate(recorded_chunks, axis=0)
        print("[*] Recording stopped.")

    sf.write(filepath, audio_data, SAMPLE_RATE)
    print(f"[+] Audio saved → {filepath}")
    return filepath


# ─────────────────────────────────────────────
# STEP 2 — TRANSCRIBE
# ─────────────────────────────────────────────

def analyze_audio(filepath: str) -> dict:
    print(f"[*] Loading Whisper model ({WHISPER_MODEL})...")
    model = whisper.load_model(WHISPER_MODEL)

    print(f"[*] Transcribing {filepath} ...")
    result = model.transcribe(filepath)

    output = {
        "file":     filepath,
        "language": result.get("language", "unknown"),
        "text":     result["text"].strip(),
        "segments": [
            {
                "start": round(s["start"], 2),
                "end":   round(s["end"], 2),
                "text":  s["text"].strip()
            }
            for s in result.get("segments", [])
        ]
    }

    print(f"[+] Language  : {output['language']}")
    print(f"[+] Transcript: {output['text']}")
    return output


# ─────────────────────────────────────────────
# STEP 3 — INTENT DETECTION
# ─────────────────────────────────────────────

def detect_intent(text: str) -> str:
    lowered = text.lower()
    for intent, keywords in INTENT_MAP.items():
        if any(kw in lowered for kw in keywords):
            print(f"[+] Intent detected : {intent}")
            return intent
    print("[!] Intent: UNKNOWN")
    return "UNKNOWN"


# ─────────────────────────────────────────────
# STEP 4 — VALIDATION
# ─────────────────────────────────────────────

def validate(text: str, intent: str) -> bool:
    if not text or not text.strip():
        print("[!] Validation FAILED — empty transcript")
        return False
    if intent == "UNKNOWN":
        print("[!] Validation FAILED — unrecognised intent")
        return False
    if len(text.strip().split()) < 2:
        print("[!] Validation FAILED — transcript too short")
        return False
    print("[+] Validation PASSED")
    return True


# ─────────────────────────────────────────────
# STEP 5 — SAVE TRANSCRIPTION
# ─────────────────────────────────────────────

def save_transcription(transcript: dict, intent: str, valid: bool) -> dict:
    ensure_file(TRANSCRIPTIONS_FILE, default_content="[]")

    with open(TRANSCRIPTIONS_FILE, "r") as f:
        try:
            records = json.load(f)
        except json.JSONDecodeError:
            records = []

    record = {
        "id":        len(records) + 1,
        "timestamp": datetime.now().isoformat(),
        "file":      transcript["file"],
        "language":  transcript["language"],
        "text":      transcript["text"],
        "intent":    intent,
        "valid":     valid,
        "segments":  transcript["segments"],
    }

    records.append(record)

    with open(TRANSCRIPTIONS_FILE, "w") as f:
        json.dump(records, f, indent=2)

    print(f"[+] Saved to {TRANSCRIPTIONS_FILE}  (record #{record['id']})")
    return record


# ─────────────────────────────────────────────
# STEP 6 — SAVE COMMAND
# ─────────────────────────────────────────────

def save_command(record: dict) -> dict | None:
    ensure_file(COMMANDS_FILE, default_content="[]")

    with open(COMMANDS_FILE, "r") as f:
        try:
            commands = json.load(f)
        except json.JSONDecodeError:
            commands = []

    if not record["valid"]:
        print(f"[!] Command not saved — record #{record['id']} is invalid")
        return None

    intent      = record["intent"]
    esp_payload = COMMAND_DISPATCH.get(intent)

    if not esp_payload:
        print(f"[!] No dispatch mapping found for intent: {intent}")
        return None

    command = {
        "id":               len(commands) + 1,
        "timestamp":        record["timestamp"],
        "transcription_id": record["id"],
        "intent":           intent,
        "esp_payload":      esp_payload,
        "mqtt_topic":       MQTT_TOPIC,
        "dispatched":       False,
    }

    commands.append(command)

    with open(COMMANDS_FILE, "w") as f:
        json.dump(commands, f, indent=2)

    print(f"[+] Command saved → {COMMANDS_FILE}")
    print(f"    Intent      : {intent}")
    print(f"    ESP payload : {json.dumps(esp_payload)}")
    return command


# ─────────────────────────────────────────────
# STEP 7 — READ LAST COMMAND & DISPATCH TO ESP
# ─────────────────────────────────────────────

def dispatch_last_command() -> bool:
    """
    Reads the LAST entry in commands.json and publishes
    its esp_payload to the EMQX broker over MQTT.
    The ESP subscribes to MQTT_TOPIC and reacts to 'action'.
    """
    ensure_file(COMMANDS_FILE, default_content="[]")

    with open(COMMANDS_FILE, "r") as f:
        try:
            commands = json.load(f)
        except json.JSONDecodeError:
            commands = []

    if not commands:
        print("[!] commands.json is empty — nothing to dispatch")
        return False

    # Always take the last saved command
    command = commands[-1]

    if command.get("dispatched"):
        print(f"[!] Last command #{command['id']} was already dispatched — skipping")
        return False

    # Build the MQTT payload
    payload = json.dumps({
        "command_id": command["id"],
        "timestamp":  command["timestamp"],
        **command["esp_payload"]    # action, target, description
    })

    try:
        # CallbackAPIVersion.VERSION2 fixes the deprecation warning
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"voice-dispatcher-{command['id']}"
        )

        if MQTT_USERNAME:
            client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code == 0:
                print("[+] Connected to EMQX broker successfully")
            else:
                print(f"[!] Connection failed — reason code: {reason_code}")

        def on_publish(client, userdata, mid, reason_code, properties):
            print(f"[+] Broker confirmed delivery (mid={mid})")

        client.on_connect = on_connect
        client.on_publish = on_publish

        print(f"[*] Connecting to EMQX broker {MQTT_BROKER}:{MQTT_PORT} ...")
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=10)
        client.loop_start()

        result = client.publish(MQTT_TOPIC, payload, qos=1)
        result.wait_for_publish()

        client.loop_stop()
        client.disconnect()

        print(f"[+] Published to topic  : '{MQTT_TOPIC}'")
        print(f"    Payload             : {payload}")

        # Mark as dispatched in commands.json
        commands[-1]["dispatched"] = True
        with open(COMMANDS_FILE, "w") as f:
            json.dump(commands, f, indent=2)

        print(f"[+] Command #{command['id']} marked as dispatched ✓")
        return True

    except Exception as e:
        print(f"[!] MQTT dispatch FAILED: {e}")
        return False


# ─────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(RECORDINGS_DIR, exist_ok=True)

    existing = [f for f in os.listdir(RECORDINGS_DIR) if f.endswith(".wav")]
    index    = len(existing) + 1
    filename = f"recording_{index}.wav"

    # 1. Record
    filepath   = record_audio(filename, duration=None)

    # 2. Transcribe
    transcript = analyze_audio(filepath)

    # 3. Detect intent
    intent     = detect_intent(transcript["text"])

    # 4. Validate
    valid      = validate(transcript["text"], intent)

    # 5. Save transcription → transcriptions.json
    record     = save_transcription(transcript, intent, valid)

    # 6. Build & save command → commands.json
    command    = save_command(record)

    # 7. Read last command from commands.json → publish to EMQX
    dispatched = dispatch_last_command()

    # 8. Summary
    print("\n─────────── PIPELINE RESULT ───────────")
    print(f"  File       : {record['file']}")
    print(f"  Transcript : {record['text']}")
    print(f"  Intent     : {record['intent']}")
    print(f"  Valid      : {record['valid']}")
    if command:
        print(f"  ESP action : {command['esp_payload']['action']}")
        print(f"  MQTT topic : {MQTT_TOPIC}")
        print(f"  Dispatched : {dispatched}")
    else:
        print("  Command    : not dispatched (invalid or unmapped intent)")
    print("────────────────────────────────────────")
