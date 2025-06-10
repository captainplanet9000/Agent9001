#!/usr/bin/env python3
"""
Simplified Flask app for Railway deployment with two-phase initialization:
1. Start quickly and pass health checks
2. Initialize the agent in the background
"""
import os
import sys
import time
import json
import socket
import subprocess
import threading
import logging
from flask import Flask, jsonify, Response, send_from_directory, request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("railway_app")

# Create Flask app
app = Flask(__name__)

# Global state to track startup progress
APP_STATE = {
    "status": "initializing",
    "ui_ready": False,
    "api_ready": False,
    "error": None
}

def run_agent_ui():
    """Run the agent UI in the background"""
    try:
        # Give the Flask app time to start first
        time.sleep(5)
        
        logger.info("Starting agent initialization...")
        APP_STATE["status"] = "starting_initialization"
        
        # Run initialization script
        logger.info("Running initialization script...")
        init_cmd = ["python3", "-u", "initialize.py"]
        init_process = subprocess.run(
            init_cmd,
            capture_output=True,
            text=True
        )
        
        if init_process.returncode != 0:
            logger.error(f"Initialization failed: {init_process.stderr}")
            APP_STATE["error"] = f"Init failed: {init_process.stderr[:200]}..."
            APP_STATE["status"] = "initialization_failed"
            return
            
        logger.info("Initialization completed successfully")
        APP_STATE["status"] = "starting_ui"
        
        # Start UI server
        logger.info("Starting UI server...")
        env = os.environ.copy()
        env["PORT"] = "8000"  # Use a different port for the internal UI
        
        ui_process = subprocess.Popen(
            ["python3", "-u", "run_ui.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            env=env
        )
        
        # Track output
        for line in ui_process.stdout:
            logger.info(f"UI: {line.strip()}")
            if "Running on" in line:
                APP_STATE["ui_ready"] = True
                APP_STATE["status"] = "ready"
                logger.info("UI server is ready!")
                
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error in agent startup: {error_msg}")
        APP_STATE["error"] = error_msg
        APP_STATE["status"] = "error"

@app.route("/", methods=["GET"])
def root():
    """Root endpoint for Railway health checks"""
    return jsonify({
        "status": "ok",
        "service": "Agent9001",
        "message": "Service is responding",
        "app_state": APP_STATE,
        "timestamp": time.time()
    }), 200

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint that always returns 200 OK for Railway health checks"""
    return jsonify({
        "status": "ok",
        "service": "Agent9001",
        "timestamp": time.time()
    }), 200

@app.route("/api/status", methods=["GET"])
def status():
    """Status endpoint with detailed information"""
    return jsonify({
        "status": APP_STATE["status"],
        "ui_ready": APP_STATE["ui_ready"],
        "api_ready": APP_STATE["api_ready"],
        "error": APP_STATE["error"],
        "timestamp": time.time(),
        "environment": {
            "python_version": sys.version,
            "hostname": socket.gethostname(),
            "port": os.environ.get("PORT", "8080")
        }
    }), 200

if __name__ == "__main__":
    # Print environment info for debugging
    logger.info("======== STARTING RAILWAY DEPLOYMENT ========")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"PORT environment variable: {os.environ.get('PORT')}")
    
    # Start UI in background thread
    ui_thread = threading.Thread(target=run_agent_ui)
    ui_thread.daemon = True  # Thread will exit when main thread exits
    ui_thread.start()
    logger.info("Started background thread for Agent initialization")
    
    # Get port from environment or use default
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting Flask server on port {port}")
    
    # Run Flask app
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
