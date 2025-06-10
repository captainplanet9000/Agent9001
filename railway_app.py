#!/usr/bin/env python3
"""
Flask app for Railway deployment that serves the Agent Zero UI.
"""
import os
import sys
import time
import json
import socket
import threading
import subprocess
import logging
import requests
from flask import Flask, jsonify, request, Response, redirect, send_from_directory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("railway_app")

# Create Flask app
app = Flask(__name__, static_folder="webui/dist", static_url_path="/")

# Global variables to track agent state
AGENT_PROCESS = None
AGENT_PORT = 8000  # Port where agent UI will run
AGENT_READY = False
AGENT_ERROR = None
AGENT_STATUS = "initializing"

def run_agent_ui():
    """Run the Agent UI in a separate thread"""
    global AGENT_PROCESS, AGENT_READY, AGENT_ERROR, AGENT_STATUS
    
    try:
        # Wait a moment for the main Flask app to start
        time.sleep(3)
        logger.info("Starting Agent Zero initialization...")
        AGENT_STATUS = "initializing"
        
        # Initialize first
        logger.info("Running initialization...")
        init_cmd = ["python", "initialize.py"]
        init_result = subprocess.run(init_cmd, 
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True)
        
        if init_result.returncode != 0:
            logger.error(f"Initialization failed: {init_result.stdout}")
            AGENT_ERROR = f"Initialization failed: {init_result.stdout[:500]}..."
            AGENT_STATUS = "initialization_failed"
            return
        
        logger.info("Initialization completed")
        AGENT_STATUS = "starting_ui"
        
        # Set the environment for the agent UI process
        env = os.environ.copy()
        env["PORT"] = str(AGENT_PORT)
        
        # Start agent UI
        logger.info(f"Starting Agent Zero UI on port {AGENT_PORT}...")
        AGENT_PROCESS = subprocess.Popen(
            ["python", "run_ui.py"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Monitor the output to detect when it's ready
        while True:
            line = AGENT_PROCESS.stdout.readline()
            if not line:
                break
                
            logger.info(f"AGENT UI: {line.strip()}")
            
            if "Running on" in line:
                logger.info("Agent UI is ready!")
                AGENT_READY = True
                AGENT_STATUS = "ready"
                break
                
            # Check if process has terminated
            if AGENT_PROCESS.poll() is not None:
                logger.error("Agent UI process terminated unexpectedly")
                AGENT_ERROR = f"Process terminated with code {AGENT_PROCESS.returncode}"
                AGENT_STATUS = "failed"
                break
        
        # Continue reading output
        while AGENT_PROCESS and AGENT_PROCESS.poll() is None:
            line = AGENT_PROCESS.stdout.readline()
            if not line:
                break
            logger.info(f"AGENT UI: {line.strip()}")
            
    except Exception as e:
        logger.error(f"Error running Agent UI: {str(e)}")
        AGENT_ERROR = str(e)
        AGENT_STATUS = "error"

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint that always returns 200 OK"""
    return jsonify({"status": "ok"}), 200

@app.route('/api/status', methods=['GET'])
def status():
    """Status endpoint for Agent Zero"""
    return jsonify({
        "status": AGENT_STATUS,
        "ready": AGENT_READY,
        "error": AGENT_ERROR,
        "timestamp": time.time(),
        "agent_process_running": AGENT_PROCESS is not None and AGENT_PROCESS.poll() is None
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Serve UI or proxy to Agent Zero"""
    if AGENT_READY:
        try:
            # Proxy to Agent Zero UI
            resp = requests.get(f"http://localhost:{AGENT_PORT}/")
            return Response(resp.content, status=resp.status_code, 
                           content_type=resp.headers.get('Content-Type'))
        except Exception as e:
            logger.error(f"Error proxying to Agent Zero UI: {e}")
            return jsonify({
                "status": "error",
                "message": "Agent Zero UI is not responding",
                "error": str(e)
            }), 500
    else:
        # Show loading page
        return jsonify({
            "status": AGENT_STATUS,
            "message": "Agent Zero is starting...",
            "ready": AGENT_READY,
            "error": AGENT_ERROR
        }), 200

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy(path):
    """Proxy all other requests to Agent Zero UI"""
    if not AGENT_READY:
        return jsonify({"status": "not_ready", "message": "Agent Zero is starting..."}), 503
        
    try:
        url = f"http://localhost:{AGENT_PORT}/{path}"
        method = request.method
        headers = {k: v for k, v in request.headers if k != 'Host'}
        data = request.get_data()
        
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            data=data,
            cookies=request.cookies,
            allow_redirects=False
        )
        
        response = Response(resp.content, status=resp.status_code)
        
        # Copy response headers
        for key, value in resp.headers.items():
            if key.lower() not in ('content-length', 'connection'):
                response.headers[key] = value
                
        return response
        
    except Exception as e:
        logger.error(f"Error proxying request to Agent Zero UI: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to connect to Agent Zero UI",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    # Print diagnostic information
    logger.info("=== AGENT ZERO RAILWAY DEPLOYMENT ===")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Current directory: {os.getcwd()}")
    logger.info(f"Files in directory: {', '.join(os.listdir('.'))}")
    
    # Start UI in a separate thread
    ui_thread = threading.Thread(target=run_agent_ui)
    ui_thread.daemon = True
    ui_thread.start()
    logger.info("Started Agent UI thread")
    
    # Run the Flask app on the PORT specified by Railway
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting main server on port {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
