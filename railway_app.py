#!/usr/bin/env python3
"""
Railway deployment app for Agent Zero v0.8.4
This app runs a proxy server that passes health checks immediately and forwards
requests to the agent-zero UI once it's running.
"""
import os
import sys
import time
import json
import threading
import subprocess
import logging
import requests
from flask import Flask, jsonify, request, Response, send_from_directory

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Use DEBUG level to capture all logs
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("railway_app")

# Global variables
AGENT_PROCESS = None
AGENT_PORT = 8000  # Port where agent UI will run
AGENT_READY = False
AGENT_ERROR = None
AGENT_STATUS = "initializing"
AGENT_VERSION = "v0.8.4"  # Target version

# Create Flask app
app = Flask(__name__, static_folder="webui/dist", static_url_path="/")

def log_directory_contents():
    """Log the contents of the current directory for debugging"""
    try:
        logger.info(f"Current directory: {os.getcwd()}")
        files = os.listdir('.')
        logger.info(f"Files in directory: {', '.join(files)}")
        
        if 'run_ui.py' in files:
            with open('run_ui.py', 'r') as f:
                logger.info(f"run_ui.py first 10 lines: {f.read(500)}")
    except Exception as e:
        logger.error(f"Error listing directory: {e}")

def run_agent_ui():
    """Run the Agent Zero UI in a separate thread"""
    global AGENT_PROCESS, AGENT_READY, AGENT_ERROR, AGENT_STATUS
    
    try:
        # Wait a moment for the main Flask app to start
        time.sleep(3)
        log_directory_contents()
        
        logger.info(f"Starting Agent Zero {AGENT_VERSION} initialization...")
        AGENT_STATUS = "initializing"
        
        # Initialize first
        logger.info("Running initialization script...")
        logger.debug("CWD before init: " + os.getcwd())
        
        # Use Popen for initialization to capture real-time output
        init_process = subprocess.Popen(
            ["python", "initialize.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Monitor initialization output
        init_success = True
        while init_process.poll() is None:
            line = init_process.stdout.readline()
            if line:
                logger.info(f"INIT: {line.strip()}")
        
        # Get final output and check return code
        remaining_output, _ = init_process.communicate()
        if remaining_output:
            logger.info(f"INIT (final): {remaining_output.strip()}")
        
        if init_process.returncode != 0:
            logger.error(f"Initialization failed with code {init_process.returncode}")
            AGENT_ERROR = f"Initialization failed with exit code {init_process.returncode}"
            AGENT_STATUS = "initialization_failed"
            return
        
        logger.info("Initialization completed successfully")
        AGENT_STATUS = "starting_ui"
        
        # Set the environment for the agent UI process - use port 8000 internally
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
        ready_detected = False
        start_time = time.time()
        
        while True:
            if AGENT_PROCESS.poll() is not None:
                if not ready_detected:
                    logger.error(f"Agent UI process terminated early with code {AGENT_PROCESS.returncode}")
                    AGENT_ERROR = f"Process terminated with code {AGENT_PROCESS.returncode}"
                    AGENT_STATUS = "failed"
                break
                
            line = AGENT_PROCESS.stdout.readline()
            if not line:
                if time.time() - start_time > 120:  # Timeout after 2 minutes
                    logger.error("Timed out waiting for Agent UI to start")
                    AGENT_ERROR = "Timeout waiting for Agent UI to start"
                    AGENT_STATUS = "timeout"
                    break
                time.sleep(0.1)
                continue
                
            logger.info(f"UI: {line.strip()}")
            
            # Look for signs that the server is ready
            if "Running on" in line or "Listening on" in line:
                logger.info("Agent UI server is ready!")
                AGENT_READY = True
                AGENT_STATUS = "ready"
                ready_detected = True
                break
        
        # Keep reading output for logging
        if AGENT_PROCESS and AGENT_PROCESS.poll() is None:
            threading.Thread(target=monitor_process_output, daemon=True).start()
            
    except Exception as e:
        logger.error(f"Error running Agent UI: {str(e)}", exc_info=True)
        AGENT_ERROR = str(e)
        AGENT_STATUS = "error"

def monitor_process_output():
    """Monitor and log the output from the Agent UI process"""
    global AGENT_PROCESS
    
    try:
        while AGENT_PROCESS and AGENT_PROCESS.poll() is None:
            line = AGENT_PROCESS.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            logger.info(f"UI: {line.strip()}")
    except Exception as e:
        logger.error(f"Error monitoring process output: {e}")

def check_agent_availability():
    """Test connection to agent on internal port"""
    try:
        response = requests.get(f"http://localhost:{AGENT_PORT}/", timeout=1)
        logger.info(f"Agent UI test response: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"Agent UI not ready yet: {e}")
        return False

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint that always returns 200 OK"""
    return jsonify({"status": "ok"}), 200

@app.route('/api/status', methods=['GET'])
def status():
    """Status endpoint with detailed information about the agent"""
    agent_available = False
    if AGENT_READY:
        agent_available = check_agent_availability()
    
    return jsonify({
        "status": AGENT_STATUS,
        "ready": AGENT_READY,
        "available": agent_available, 
        "error": AGENT_ERROR,
        "timestamp": time.time(),
        "version": AGENT_VERSION,
        "agent_process_running": AGENT_PROCESS is not None and AGENT_PROCESS.poll() is None
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Root endpoint - either proxy to Agent Zero or show loading status"""
    if AGENT_READY and check_agent_availability():
        try:
            # Proxy to Agent Zero UI
            resp = requests.get(f"http://localhost:{AGENT_PORT}/", timeout=5)
            return Response(resp.content, status=resp.status_code, 
                           content_type=resp.headers.get('Content-Type', 'text/html'))
        except Exception as e:
            logger.error(f"Error proxying to Agent Zero UI: {e}")
            return jsonify({
                "status": "error",
                "message": "Agent Zero UI is running but not responding",
                "error": str(e)
            }), 500
    else:
        # Show loading page
        return jsonify({
            "status": AGENT_STATUS,
            "message": f"Agent Zero {AGENT_VERSION} is starting...",
            "ready": AGENT_READY,
            "error": AGENT_ERROR
        }), 200

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def proxy(path):
    """Proxy all other requests to Agent Zero UI"""
    if not AGENT_READY or not check_agent_availability():
        return jsonify({
            "status": "not_ready", 
            "message": f"Agent Zero {AGENT_VERSION} is starting..."
        }), 503
        
    try:
        url = f"http://localhost:{AGENT_PORT}/{path}"
        method = request.method
        headers = {k: v for k, v in request.headers if k.lower() != 'host'}
        data = request.get_data()
        
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            data=data,
            cookies=request.cookies,
            allow_redirects=False,
            timeout=30
        )
        
        response = Response(resp.content, status=resp.status_code)
        
        # Copy response headers
        for key, value in resp.headers.items():
            if key.lower() not in ('content-length', 'connection', 'transfer-encoding'):
                response.headers[key] = value
                
        return response
        
    except Exception as e:
        logger.error(f"Error proxying request to Agent Zero UI: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to proxy request to Agent Zero UI",
            "error": str(e),
            "path": path
        }), 500

if __name__ == "__main__":
    # Print diagnostic information
    logger.info(f"=== AGENT ZERO {AGENT_VERSION} RAILWAY DEPLOYMENT ===")
    logger.info(f"Python version: {sys.version}")
    log_directory_contents()
    
    # Start UI in a separate thread
    ui_thread = threading.Thread(target=run_agent_ui)
    ui_thread.daemon = True
    ui_thread.start()
    logger.info("Started Agent Zero UI thread")
    
    # Run the Flask app on the PORT specified by Railway
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting main server on port {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
