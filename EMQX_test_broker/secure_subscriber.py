# This is the final, production-ready code for your project.
# It enforces Mutual TLS (MTLS), meaning the client MUST present a certificate 
# to the broker, matching your EMQX configuration on port 8883.

import paho.mqtt.client as mqtt
import ssl
import time
import os 

# --- Configuration Matching Your EMQX Project Config ---
BROKER_ADDRESS = "192.168.1.2" # Replace with your EMQX IP address
BROKER_PORT = 8883
TOPIC_TO_SUBSCRIBE = "test/secure"

# --------------------------------------------------------------------------------
# !!! CRITICAL: NO PATH EDITING REQUIRED. ENSURE FILES ARE IN THIS DIRECTORY. !!!
# --------------------------------------------------------------------------------

# 1. Your CA certificate (USED TO VERIFY THE BROKER)
# Path assumes the file is in the same directory as this script.
CA_CERT_PATH = "./ca.pem" # <--- CHANGED FROM ca.crt to ca.pem (example fix)
# 2. Your client's certificate (REQUIRED FOR MTLS AUTHENTICATION)
CLIENT_CERT_PATH = "./client.pem" # <--- CHANGED FROM client.crt to client.pem (example fix)
# 3. Your client's private key
CLIENT_KEY_PATH = "./client.key" # <--- KEEP .key, usually standard 
# --------------------------------------------------------------------------------

def validate_path_exists(path, label):
    """Checks if a given file path exists and raises a descriptive error if not."""
    if not path or not os.path.exists(path):
        # This error handles both the empty string case and the file not being present.
        raise FileNotFoundError(f"Missing required file for {label}: '{path}'.\n\t*** ACTION REQUIRED: Please ensure the file is in the SAME directory as the script. ***")

def on_connect(client, userdata, flags, rc):
    """Callback triggered upon connection to the broker."""
    if rc == 0:
        print(f"✅ Connected successfully to EMQX on port {BROKER_PORT}. FULL MTLS SUCCESS.")
        client.subscribe(TOPIC_TO_SUBSCRIBE)
        print(f"✅ Subscribed to topic: {TOPIC_TO_SUBSCRIBE}")
    else:
        print(f"❌ Connection failed with result code {rc}")
        print("   HINT: The certificates may be expired or the broker is rejecting the client's credentials.")

def on_message(client, userdata, msg):
    """Callback triggered when a message is received."""
    print(f"\n[RECEIVED SECURE MESSAGE]")
    print(f"Topic: {msg.topic}")
    print(f"Payload: {msg.payload.decode()}")

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="PythonSecureClient")
    client.on_connect = on_connect
    client.on_message = on_message
    
    # --- File Path Validation Checks ---
    validate_path_exists(CA_CERT_PATH, "CA Certificate")
    validate_path_exists(CLIENT_CERT_PATH, "Client Certificate")
    validate_path_exists(CLIENT_KEY_PATH, "Client Key")
    
    # --- Configure Full Mutual TLS (MTLS) ---
    client.tls_set(
        ca_certs=CA_CERT_PATH,
        certfile=CLIENT_CERT_PATH, 
        keyfile=CLIENT_KEY_PATH,   
        cert_reqs=ssl.CERT_REQUIRED, 
        tls_version=ssl.PROTOCOL_TLSv1_2 
    )
    
    print(f"Attempting to connect to {BROKER_ADDRESS}:{BROKER_PORT} with FULL MTLS...")
    client.connect(BROKER_ADDRESS, BROKER_PORT)
    
    # Start a loop in the background to handle network traffic and callbacks
    client.loop_forever()

except FileNotFoundError as e:
    # This exception handler will catch the specific error from validate_path_exists
    print(f"\n❌ FATAL ERROR: Required certificate file path is missing or incorrect.")
    print(f"   DETAIL: {e}")
    print("   Please ensure the files ca.crt, client.crt, and client.key are in the current directory.")
except Exception as e:
    print(f"\n❌ An unexpected error occurred: {e}")
    client.loop_stop()
