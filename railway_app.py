#!/usr/bin/env python3
"""
Ultra-minimal Flask app for Railway health checks.
This simple app does nothing but respond to health checks to ensure deployment succeeds.
"""
import os
import sys
import flask

# Create the most minimal Flask app possible
app = flask.Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    return flask.jsonify({"status": "ok", "message": "Agent9001 is running"})

@app.route('/health', methods=['GET'])
def health():
    return flask.jsonify({"status": "ok"})

if __name__ == '__main__':
    # Print diagnostic information
    print("=== MINIMAL RAILWAY DEPLOYMENT ===")
    print(f"Python version: {sys.version}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Files in directory: {os.listdir('.')}")
    print(f"PORT env var: {os.environ.get('PORT')}")
    sys.stdout.flush()
    
    # Run the Flask app on the PORT specified by Railway
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
