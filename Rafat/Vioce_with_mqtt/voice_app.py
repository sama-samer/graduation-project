#!/usr/bin/env python3
"""
voice_app_console.py — Voice Command Pipeline (console only)

Run:
    python3 voice_app_console.py

Install:
    pip install openai-whisper sounddevice soundfile numpy paho-mqtt psycopg2-binary

Linux:
    sudo apt install portaudio19-dev

This version:
- has no UI at all
- prints everything to terminal
- records audio from microphone
- transcribes with Whisper (English Only)
- extracts machine ID (Concatenates all spoken digits, e.g. "3,100 and 1" -> 31001)
- detects intent (Updated with Whisper misspellings like "vault" for "volt")
- validates command
- saves JSON records
- publishes MQTT payload in the exact format required by your DB listener
"""

import os
import re
import json
import time
import threading
from datetime import datetime

import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper
import paho.mqtt.client as mqtt


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
CHANNELS = 1
RECORDINGS_DIR = "recordings"
TRANSCRIPTIONS_FILE = "transcriptions.json"
COMMANDS_FILE = "commands.json"

WHISPER_MODEL = "tiny"   # tiny | base | small | medium | large

# Match your MQTT receiver
MQTT_BROKER = "192.168.1.8"
MQTT_PORT = 1884
MQTT_USERNAME = ""
MQTT_PASSWORD = ""
MQTT_TOPIC = "employees/15792/recorder"

PREFERRED_SAMPLE_RATES = (16000, 22050, 32000, 44100, 48000)

INTENT_MAP = {
    "MEASURE": [
        "measure", "read", "get", "fetch", "show", "check",
        "sensor", "reading", "data", "value", "report", "analyze", "analyse", "analysis",
        "ampere", "current", "volt", "voltage", "vault", "temperature", "temp",
    ],
    "ORDER": [
        "open", "start", "launch", "turn on", "activate", "enable",
        "close", "stop", "shut", "turn off", "deactivate",
        "produce", "make", "manufacture", "build", "create",
    ],
}

SENSOR_KEYWORDS = {
    "ampere": ["ampere", "amp", "amps", "current", "milliamp"],
    "volt": ["volt", "volts", "voltage", "millivolt", "vault", "vaults"],
    "temperature": ["temperature", "temp", "celsius", "fahrenheit", "heat", "degree"],
    "production": ["production", "produced", "output", "pieces produced", "manufactured"],
}

ORDER_KEYWORDS = {
    "open": ["open", "start", "launch", "turn on", "activate", "enable", "begin", "run"],
    "close": ["close", "stop", "shut", "turn off", "deactivate", "end", "disable"],
    "produce": ["produce", "make", "manufacture", "build", "create"],
}

COMMAND_DISPATCH = {
    "MEASURE_AMPERE":      {"action": "READ_AMPERE",      "target": "sensor_ampere",      "description": "Read ampere (current) sensor value"},
    "MEASURE_VOLT":        {"action": "READ_VOLT",        "target": "sensor_volt",        "description": "Read voltage sensor value"},
    "MEASURE_TEMPERATURE": {"action": "READ_TEMPERATURE", "target": "sensor_temperature", "description": "Read temperature sensor value"},
    "MEASURE_PRODUCTION":  {"action": "READ_PRODUCTION",   "target": "sensor_production",  "description": "Read production count sensor value"},
    "MEASURE_ALL":         {"action": "READ_ALL_SENSORS",  "target": "sensors",            "description": "Read all sensor values"},
    "ORDER_OPEN":          {"action": "OPEN",              "target": "system",             "description": "Open / initialize the system"},
    "ORDER_CLOSE":         {"action": "CLOSE",             "target": "system",             "description": "Close / shut down the system"},
    "ORDER_PRODUCE":       {"action": "PRODUCE",           "target": "production_line",    "description": "Produce a specified number of pieces"},
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def log(level: str, message: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {level} {message}")


def ensure_file(filepath: str, default_content: str = ""):
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(default_content)


def choose_input_device() -> tuple[int | None, dict | None]:
    try:
        default = sd.default.device
        default_in = default[0] if isinstance(default, tuple) else default
        if default_in is not None:
            info = sd.query_devices(default_in)
            if int(info.get("max_input_channels", 0)) > 0:
                return int(default_in), info
    except Exception:
        pass

    try:
        for idx, info in enumerate(sd.query_devices()):
            if int(info.get("max_input_channels", 0)) > 0:
                return idx, info
    except Exception:
        pass

    return None, None


def choose_samplerate(device_index: int | None) -> int:
    if device_index is None:
        return SAMPLE_RATE

    try:
        info = sd.query_devices(device_index, "input")
    except Exception:
        info = None

    rates = list(PREFERRED_SAMPLE_RATES)
    if info and info.get("default_samplerate"):
        rates.append(int(info["default_samplerate"]))

    seen = set()
    for rate in rates:
        if rate in seen:
            continue
        seen.add(rate)
        try:
            sd.check_input_settings(device=device_index, channels=CHANNELS, samplerate=rate, dtype="float32")
            return int(rate)
        except Exception:
            continue

    if info and info.get("default_samplerate"):
        return int(info["default_samplerate"])
    return SAMPLE_RATE


# ─────────────────────────────────────────────────────────────────────────────
# MACHINE ID
# ─────────────────────────────────────────────────────────────────────────────

def extract_machine_id(transcript_text: str) -> tuple[str, str]:
    text = transcript_text.strip()
    
    # Capture digits, spaces, commas, hyphens, and the word "and" following "machine"
    pattern = re.compile(r"\bmachine\s+((?:(?:\d+|and)[\s,\-]*)+)", re.IGNORECASE)
    match = pattern.search(text)
    
    if match:
        raw_sequence = match.group(1)
        
        # Extract purely the digits from the matched sequence
        digits = re.findall(r'\d+', raw_sequence)
        
        if digits:
            # Concatenate all parsed digits (e.g., ["3100", "1"] becomes "31001")
            machine_id = "".join(digits)
            
            # Find the end position of the last digit so we don't accidentally cut too much text
            last_digit_match = list(re.finditer(r'\d', raw_sequence))
            if last_digit_match:
                last_digit_idx = last_digit_match[-1].end()
                end_idx = match.start(1) + last_digit_idx
                
                # Cut the matched machine ID block out of the original text
                remaining = text[:match.start()] + " " + text[end_idx:]
                remaining = re.sub(r'\s+', ' ', remaining).strip()
                
                return machine_id, remaining

    # Fallback for standard alphanumeric IDs (e.g., "A123")
    alpha_pattern = re.compile(r"\bmachine\s+([A-Z0-9_\-]+)", re.IGNORECASE)
    match_alpha = alpha_pattern.search(text)
    
    if match_alpha:
        machine_id = match_alpha.group(1).upper()
        remaining = text[:match_alpha.start()] + " " + text[match_alpha.end():]
        return machine_id, remaining.strip()

    # Default ID if nothing is found
    return "99999", text


# ─────────────────────────────────────────────────────────────────────────────
# WHISPER
# ─────────────────────────────────────────────────────────────────────────────

_WHISPER_MODEL_CACHE = None
_WHISPER_MODEL_LOCK = threading.Lock()


def get_whisper_model():
    global _WHISPER_MODEL_CACHE
    with _WHISPER_MODEL_LOCK:
        if _WHISPER_MODEL_CACHE is None:
            log("[*]", f"Loading Whisper model ({WHISPER_MODEL})...")
            _WHISPER_MODEL_CACHE = whisper.load_model(WHISPER_MODEL)
            log("[+]", "Whisper model loaded")
        return _WHISPER_MODEL_CACHE


def analyze_audio(filepath: str, model=None) -> dict:
    if model is None:
        model = get_whisper_model()

    # language="en" enforces English output
    result = model.transcribe(filepath, fp16=False, language="en")

    output = {
        "file": filepath,
        "language": result.get("language", "unknown"),
        "text": result["text"].strip(),
        "segments": [
            {
                "start": round(s["start"], 2),
                "end": round(s["end"], 2),
                "text": s["text"].strip(),
            }
            for s in result.get("segments", [])
        ],
    }

    return output


# ─────────────────────────────────────────────────────────────────────────────
# INTENT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_quantity(text: str) -> int | None:
    m = re.search(r"\b(\d+)\s*(?:piece|pieces|unit|units|item|items)?\b", text)
    if m:
        return int(m.group(1))

    word_numbers = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    }
    for word, val in word_numbers.items():
        if re.search(rf"\b{word}\b", text, re.IGNORECASE):
            return val
    return None


def detect_intent(text: str) -> dict:
    lowered = text.lower()
    result = {
        "intent": "UNKNOWN",
        "action_key": None,
        "sensor_type": None,
        "order_type": None,
        "quantity": None,
    }

    matched_intent = None
    for intent, keywords in INTENT_MAP.items():
        if any(kw in lowered for kw in keywords):
            matched_intent = intent
            break

    if not matched_intent:
        return result

    result["intent"] = matched_intent

    if matched_intent == "MEASURE":
        for sensor, keywords in SENSOR_KEYWORDS.items():
            if any(kw in lowered for kw in keywords):
                result["sensor_type"] = sensor
                result["action_key"] = f"MEASURE_{sensor.upper()}"
                return result

        result["sensor_type"] = "all"
        result["action_key"] = "MEASURE_ALL"
        return result

    if matched_intent == "ORDER":
        for order_type, keywords in ORDER_KEYWORDS.items():
            if any(kw in lowered for kw in keywords):
                result["order_type"] = order_type
                result["action_key"] = f"ORDER_{order_type.upper()}"
                if order_type == "produce":
                    result["quantity"] = extract_quantity(text)
                return result

        result["order_type"] = "unknown"
        result["action_key"] = "ORDER_OPEN"
        return result

    return result


def validate(text: str, intent_info: dict) -> bool:
    if not text or not text.strip():
        return False
    if intent_info["intent"] == "UNKNOWN":
        return False
    if len(text.strip().split()) < 2:
        return False
    if intent_info["intent"] == "ORDER" and intent_info["order_type"] == "produce":
        if intent_info["quantity"] is None:
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SAVE JSON
# ─────────────────────────────────────────────────────────────────────────────

def save_transcription(transcript: dict, intent_info: dict, valid: bool,
                       employee_id: str, command_text: str) -> dict:
    ensure_file(TRANSCRIPTIONS_FILE, default_content="[]")
    with open(TRANSCRIPTIONS_FILE, "r", encoding="utf-8") as f:
        try:
            records = json.load(f)
        except Exception:
            records = []

    record = {
        "id": len(records) + 1,
        "timestamp": datetime.now().isoformat(),
        "employee_id": employee_id,
        "machine_id": transcript.get("machine_id", "99999"),
        "file": transcript["file"],
        "language": transcript["language"],
        "raw_text": transcript["text"],
        "command_text": command_text,
        "intent": intent_info["intent"],
        "action_key": intent_info["action_key"],
        "sensor_type": intent_info["sensor_type"],
        "order_type": intent_info["order_type"],
        "quantity": intent_info["quantity"],
        "valid": valid,
        "segments": transcript["segments"],
    }

    records.append(record)
    with open(TRANSCRIPTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    return record


def save_command(record: dict) -> dict | None:
    ensure_file(COMMANDS_FILE, default_content="[]")
    with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
        try:
            commands = json.load(f)
        except Exception:
            commands = []

    if not record["valid"]:
        return None

    action_key = record["action_key"]
    esp_payload = COMMAND_DISPATCH.get(action_key)
    if not esp_payload:
        return None

    enriched = dict(esp_payload)
    if record["sensor_type"] and record["sensor_type"] != "all":
        enriched["sensor_type"] = record["sensor_type"]
    if record["order_type"] == "produce" and record["quantity"] is not None:
        enriched["quantity"] = record["quantity"]

    command = {
        "id": len(commands) + 1,
        "timestamp": record["timestamp"],
        "employee_id": record["employee_id"],
        "machine_id": record["machine_id"],
        "transcription_id": record["id"],
        "intent": record["intent"],
        "speech_text": record["raw_text"],
        "action_key": action_key,
        "command": enriched,
        "mqtt": {"topic": MQTT_TOPIC, "dispatched": False},
    }

    commands.append(command)
    with open(COMMANDS_FILE, "w", encoding="utf-8") as f:
        json.dump(commands, f, indent=2)

    return command


# ─────────────────────────────────────────────────────────────────────────────
# MQTT
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_last_command() -> bool:
    ensure_file(COMMANDS_FILE, default_content="[]")
    with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
        try:
            commands = json.load(f)
        except Exception:
            commands = []

    if not commands:
        log("[!]", "commands.json is empty — nothing to dispatch")
        return False

    command = commands[-1]
    if command.get("mqtt", {}).get("dispatched"):
        log("[!]", f"Command #{command['id']} already dispatched — skipping")
        return False

    payload = {
        "employee_id": str(command.get("employee_id") or "15792"),
        "machine_id": command.get("machine_id"),
        "speech_text": command.get("speech_text", ""),
        "intent": command.get("intent"),
        "Action": command.get("command", {}).get("action"),
    }

    payload_text = json.dumps(payload, ensure_ascii=False)

    try:
        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"voice-dispatcher-{command['id']}",
            )
        except Exception:
            client = mqtt.Client(client_id=f"voice-dispatcher-{command['id']}")

        if MQTT_USERNAME:
            client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=10)
        client.loop_start()
        result = client.publish(MQTT_TOPIC, payload_text, qos=1)
        result.wait_for_publish()
        client.loop_stop()
        client.disconnect()

        commands[-1]["mqtt"]["dispatched"] = True
        with open(COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(commands, f, indent=2)

        return True

    except Exception as e:
        log("[!]", f"MQTT dispatch FAILED: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# AUDIO RECORDING
# ─────────────────────────────────────────────────────────────────────────────

def record_audio():
    device_index, device_info = choose_input_device()
    samplerate = choose_samplerate(device_index)

    if device_index is None:
        raise RuntimeError("No input microphone device found")

    chunks = []
    lock = threading.Lock()
    start_time = time.time()

    def audio_callback(indata, frames, t, status):
        if indata is None or len(indata) == 0:
            return
        with lock:
            chunks.append(indata.copy())

    log("[*]", "Recording started. Press Enter to stop.")
    stream = sd.InputStream(
        samplerate=samplerate,
        channels=CHANNELS,
        dtype="float32",
        callback=audio_callback,
        device=device_index,
        blocksize=1024,
        latency="low",
    )

    try:
        stream.start()
        try:
            input()
        except EOFError:
            time.sleep(5)
    finally:
        try:
            stream.stop()
        finally:
            stream.close()

    duration = round(time.time() - start_time)

    with lock:
        local_chunks = list(chunks)

    if not local_chunks:
        raise RuntimeError("No audio captured")

    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    filepath = os.path.join(RECORDINGS_DIR, f"recording_{int(time.time())}.wav")

    audio_data = np.concatenate(local_chunks, axis=0)
    sf.write(filepath, audio_data, samplerate)
    return filepath, samplerate, duration


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def process_file(filepath: str, samplerate: int, employee_id: str) -> dict:
    transcript = analyze_audio(filepath)

    machine_id, command_text = extract_machine_id(transcript["text"])
    transcript["machine_id"] = machine_id

    intent_info = detect_intent(command_text)
    valid = validate(command_text, intent_info)

    record = save_transcription(
        transcript=transcript,
        intent_info=intent_info,
        valid=valid,
        employee_id=employee_id,
        command_text=command_text,
    )

    command = save_command(record)

    output_payload = {
        "employee_id": employee_id,
        "machine_id": machine_id,
        "speech_text": transcript["text"],
        "intent": intent_info["intent"],
        "Action": command["command"]["action"] if command and "command" in command else "UNKNOWN_ACTION"
    }

    print("\n--- Output ---")
    print(json.dumps(output_payload, indent=2, ensure_ascii=False))
    
    return output_payload

def process_text_direct(speech_text: str, employee_id: str) -> dict:
    machine_id, command_text = extract_machine_id(speech_text)
    
    intent_info = detect_intent(command_text)
    action_key = intent_info.get("action_key")
    action = COMMAND_DISPATCH.get(action_key, {}).get("action", "UNKNOWN_ACTION") if action_key else "UNKNOWN_ACTION"
    
    output_payload = {
        "employee_id": employee_id,
        "machine_id": machine_id,
        "speech_text": speech_text,
        "intent": intent_info.get("intent", "UNKNOWN"),
        "Action": action
    }
    
    print("\n--- Output ---")
    print(json.dumps(output_payload, indent=2, ensure_ascii=False))
    
    return output_payload

def main():
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    ensure_file(TRANSCRIPTIONS_FILE, default_content="[]")
    ensure_file(COMMANDS_FILE, default_content="[]")

    employee_id = input("Enter EMPLOYEE ID (default 15792): ").strip() or "15792"

    while True:
        print("\nChoose action:")
        print("  r = record and analyze")
        print("  d = dispatch last saved command")
        print("  t = test direct text input (Prints specific JSON)")
        print("  q = quit")
        choice = input("> ").strip().lower()

        if choice == "q":
            break

        if choice == "d":
            dispatch_last_command()
            continue

        if choice == "t":
            test_str = input("Enter phrase to test (e.g. 'machine 3-1-0-1 read temperature'): ")
            if not test_str:
                test_str = "machine 3-1-0-1 read temperature"
            process_text_direct(test_str, employee_id)
            continue

        if choice == "r" or choice == "":
            try:
                filepath, samplerate, duration = record_audio()
                process_file(filepath, samplerate, employee_id)

                send = input("Dispatch last command to MQTT? [y/N]: ").strip().lower()
                if send == "y":
                    dispatch_last_command()

            except KeyboardInterrupt:
                log("[!]", "Interrupted by user")
            except Exception as e:
                log("[!]", f"Error: {e}")
            continue


if __name__ == "__main__":
    main()
