import whisper
import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import json
from datetime import datetime

# --- CONFIG ---
SAMPLE_RATE         = 16000
CHANNELS            = 1
RECORDINGS_DIR      = "recordings"
TRANSCRIPTIONS_FILE = "transcriptions.json"
COMMANDS_FILE       = "commands.json"
WHISPER_MODEL       = "base"

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

# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────

def ensure_file(filepath: str):
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            json.dump([], f)

# ─────────────────────────────────────────────
# RECORD AUDIO
# ─────────────────────────────────────────────

def record_audio(filename: str) -> str:
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    filepath = os.path.join(RECORDINGS_DIR, filename)

    print("[*] Recording... Press Enter to stop")

    recorded_chunks = []

    def callback(indata, frames, time, status):
        recorded_chunks.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        dtype="float32", callback=callback):
        input()

    audio_data = np.concatenate(recorded_chunks, axis=0)
    sf.write(filepath, audio_data, SAMPLE_RATE)

    print(f"[+] Saved → {filepath}")
    return filepath

# ─────────────────────────────────────────────
# TRANSCRIBE
# ─────────────────────────────────────────────

def analyze_audio(filepath: str) -> dict:
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(filepath)

    return {
        "file": filepath,
        "text": result["text"].strip(),
        "language": result.get("language", "unknown"),
        "segments": result.get("segments", [])
    }

# ─────────────────────────────────────────────
# INTENT
# ─────────────────────────────────────────────

def detect_intent(text: str) -> str:
    lowered = text.lower()

    for intent, keywords in INTENT_MAP.items():
        if any(k in lowered for k in keywords):
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

def save_transcription(transcript, intent, valid):
    ensure_file(TRANSCRIPTIONS_FILE)

    with open(TRANSCRIPTIONS_FILE, "r") as f:
        data = json.load(f)

    record = {
        "id": len(data) + 1,
        "timestamp": datetime.now().isoformat(),
        **transcript,
        "intent": intent,
        "valid": valid
    }

    data.append(record)

    with open(TRANSCRIPTIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)

    return record

# ─────────────────────────────────────────────
# SAVE COMMAND (FINAL OUTPUT)
# ─────────────────────────────────────────────

def save_command(record):
    ensure_file(COMMANDS_FILE)

    with open(COMMANDS_FILE, "r") as f:
        data = json.load(f)

    if not record["valid"]:
        print("[!] Invalid record — not saved to commands.json")
        return None

    payload = COMMAND_DISPATCH.get(record["intent"])

    if not payload:
        print("[!] No command mapping found")
        return None

    command = {
        "id": len(data) + 1,
        "timestamp": record["timestamp"],
        "transcription_id": record["id"],

        # 🔥 FINAL OUTPUT DATA
        "text": record["text"],
        "intent": record["intent"],
        "valid": record["valid"],

        "esp_payload": payload,
        "dispatched": False
    }

    data.append(command)

    with open(COMMANDS_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"[+] Saved to {COMMANDS_FILE}")

    return command

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(RECORDINGS_DIR, exist_ok=True)

    filename = f"recording.wav"

    filepath = record_audio(filename)
    transcript = analyze_audio(filepath)

    intent = detect_intent(transcript["text"])
    valid = validate(transcript["text"], intent)

    record = save_transcription(transcript, intent, valid)
    command = save_command(record)

    print("\n──── RESULT ────")
    print(f"Text     : {record['text']}")
    print(f"Intent   : {record['intent']}")
    print(f"Valid    : {record['valid']}")

    if command:
        print(f"Saved to commands.json → ID {command['id']}")
    else:
        print("Command not saved")