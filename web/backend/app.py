# Backend Python Application
# This is where you can add your Python backend logic

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return jsonify({"message": "Backend server is running!"})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    # Basic authentication logic (you can modify this)
    if username == 123 and password == 15841:
        return jsonify({"success": True, "message": "Login successful!"})
    else:
        return jsonify({"success": False, "message": "Invalid credentials"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
