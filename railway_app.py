#!/usr/bin/env python3
"""
Simple Railway wrapper for Agent Zero v0.8.4
Runs directly on Railway's PORT and adds a health check endpoint
"""
import os
import sys
import subprocess
import logging
import threading
import time
import requests
from flask import Flask, jsonify, Response, render_template, redirect

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("railway_app")

# Create minimal Flask app
app = Flask(__name__)

# Global variables
AGENT_VERSION = "v0.8.4"
AGENT_INITIALIZED = False
HEALTH_CHECK_STARTED = False

def run_initialize():
    """Run the initialization script first"""
    global AGENT_INITIALIZED
    
    try:
        logger.info("Running agent-zero initialization...")
        result = subprocess.run(
            ["python", "initialize.py"], 
            capture_output=True, 
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"Initialization failed: {result.stderr}")
            return False
        else:
            logger.info("Initialization complete")
            AGENT_INITIALIZED = True
            return True
    except Exception as e:
        logger.error(f"Error during initialization: {str(e)}")
        return False

# Set up the health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Railway"""
    global HEALTH_CHECK_STARTED
    HEALTH_CHECK_STARTED = True
    return jsonify({"status": "ok"}), 200

@app.route('/', methods=['GET'])
def redirect_to_agent():
    """Redirect to /ui/ which is where Agent Zero serves its UI"""
    return redirect("/ui/")

if __name__ == "__main__":
    # Log diagnostics
    logger.info(f"=== AGENT ZERO {AGENT_VERSION} RAILWAY DEPLOYMENT ===")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Current directory: {os.getcwd()}")
    logger.info(f"Directory contents: {', '.join(os.listdir('.'))}")
    
    # Get PORT from Railway environment
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Using port: {port}")
    
    # Run initialization in a separate thread
    init_thread = threading.Thread(target=run_initialize)
    init_thread.daemon = True
    init_thread.start()
    
    # Start health check server in a separate thread
    health_thread = threading.Thread(
        target=app.run,
        kwargs={"host": "0.0.0.0", "port": port, "debug": False, "threaded": True}
    )
    health_thread.daemon = True
    health_thread.start()
    
    # Wait for initialization to complete
    while not AGENT_INITIALIZED and init_thread.is_alive():
        logger.info("Waiting for initialization to complete...")
        time.sleep(5)
    
    if not AGENT_INITIALIZED:
        logger.error("Initialization failed or timed out")
        sys.exit(1)
    
    # Wait for health check to be hit at least once
    wait_time = 0
    while not HEALTH_CHECK_STARTED and wait_time < 60:
        logger.info("Waiting for first health check...")
        time.sleep(5)
        wait_time += 5
    
    # Now directly run the agent-zero UI
    logger.info("Starting Agent Zero UI...")
    os.environ["PORT"] = str(port)  # Make sure agent uses same port
    
    try:
        # Run UI without the wrapper Flask app
        os.execvp("python", ["python", "run_ui.py"])
    except Exception as e:
        logger.error(f"Failed to start Agent Zero UI: {str(e)}")
        sys.exit(1)
