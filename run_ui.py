import os
import sys
import time
import socket
import struct
import asyncio
from functools import wraps
import threading
import signal
import json
import traceback
from flask import Flask, request, Response, jsonify
from flask_basicauth import BasicAuth
from python.helpers import errors, files, git
from python.helpers.files import get_abs_path
from python.helpers import persist_chat, runtime, dotenv, process
from python.helpers.cloudflare_tunnel import CloudflareTunnel
from python.helpers.extract_tools import load_classes_from_folder
from python.helpers.api import ApiHandler
from python.helpers.job_loop import run_loop
from python.helpers.print_style import PrintStyle
from python.helpers.task_scheduler import TaskScheduler
from python.helpers.defer import DeferredTask

# Set the new timezone to 'UTC'
os.environ["TZ"] = "UTC"
# Apply the timezone change
time.tzset()

# initialize the internal Flask server
app = Flask("app", static_folder=get_abs_path("./webui"), static_url_path="/")
app.config["JSON_SORT_KEYS"] = False  # Disable key sorting in jsonify

lock = threading.Lock()

# Set up basic authentication
basic_auth = BasicAuth(app)


def is_loopback_address(address):
    loopback_checker = {
        socket.AF_INET: lambda x: struct.unpack("!I", socket.inet_aton(x))[0]
        >> (32 - 8)
        == 127,
        socket.AF_INET6: lambda x: x == "::1",
    }
    address_type = "hostname"
    try:
        socket.inet_pton(socket.AF_INET6, address)
        address_type = "ipv6"
    except socket.error:
        try:
            socket.inet_pton(socket.AF_INET, address)
            address_type = "ipv4"
        except socket.error:
            address_type = "hostname"

    if address_type == "ipv4":
        return loopback_checker[socket.AF_INET](address)
    elif address_type == "ipv6":
        return loopback_checker[socket.AF_INET6](address)
    else:
        for family in (socket.AF_INET, socket.AF_INET6):
            try:
                r = socket.getaddrinfo(address, None, family, socket.SOCK_STREAM)
            except socket.gaierror:
                return False
            for family, _, _, _, sockaddr in r:
                if not loopback_checker[family](sockaddr[0]):
                    return False
        return True


def requires_api_key(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        valid_api_key = dotenv.get_dotenv_value("API_KEY")
        if api_key := request.headers.get("X-API-KEY"):
            if api_key != valid_api_key:
                return Response("API key required", 401)
        elif request.json and request.json.get("api_key"):
            api_key = request.json.get("api_key")
            if api_key != valid_api_key:
                return Response("API key required", 401)
        else:
            return Response("API key required", 401)
        return await f(*args, **kwargs)

    return decorated


# allow only loopback addresses
def requires_loopback(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        if not is_loopback_address(request.remote_addr):
            return Response(
                "Access denied.",
                403,
                {},
            )
        return await f(*args, **kwargs)

    return decorated


# require authentication for handlers
def requires_auth(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        # Skip auth in Railway environment
        if os.environ.get("RAILWAY") == "true":
            return await f(*args, **kwargs)
            
        user = dotenv.get_dotenv_value("AUTH_LOGIN")
        password = dotenv.get_dotenv_value("AUTH_PASSWORD")
        if user and password:
            auth = request.authorization
            if not auth or not (auth.username == user and auth.password == password):
                return Response(
                    "Could not verify your access level for that URL.\n"
                    "You have to login with proper credentials",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Login Required"'},
                )
        return await f(*args, **kwargs)

    return decorated


# Simple health check endpoint for Railway
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint that always returns 200 OK for Railway deployment.
    This endpoint is intentionally simple and has no dependencies on other parts of the system.
    """
    try:
        return jsonify({"status": "ok", "message": "Agent9001 is running", "timestamp": time.time()}), 200
    except Exception as e:
        # Even if jsonify fails, we need to return a successful response
        return Response('{"status":"ok"}', status=200, mimetype='application/json')

# handle default address, load index and provide health check capability
@app.route("/", methods=["GET"])
async def serve_index():
    """Handle root path requests.
    Serves as both a health check endpoint for Railway deployment and serves the index page normally.
    """
    # Check if request is from Railway health check
    is_health_check = 'Railway' in request.headers.get('User-Agent', '')
    is_railway = os.environ.get("RAILWAY") == "true"
    
    # Special handling for Railway health checks
    if is_railway and is_health_check:
        try:
            return jsonify({"status": "ok", "message": "Agent9001 root health check passed", "timestamp": time.time()}), 200
        except Exception:
            return Response('{"status":"ok"}', status=200, mimetype='application/json')
    
    # For non-health check requests, apply auth and proceed to normal handling
    # Skip auth in Railway environment entirely
    if os.environ.get("RAILWAY") == "true":
        pass  # No authentication required in Railway environment
    else:
        # Check authentication for non-Railway environments
        user = dotenv.get_dotenv_value("AUTH_LOGIN")
        password = dotenv.get_dotenv_value("AUTH_PASSWORD")
        if user and password:
            auth = request.authorization
            if not auth or not (auth.username == user and auth.password == password):
                return Response(
                    "Could not verify your access level for that URL.\n"
                    "You have to login with proper credentials",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Login Required"'},
                )
    gitinfo = None
    try:
        gitinfo = git.get_git_info()
    except Exception:
        gitinfo = {
            "version": "unknown",
            "commit_time": "unknown",
        }
    return files.read_file(
        "./webui/index.html",
        version_no=gitinfo["version"],
        version_time=gitinfo["commit_time"],
    )


def run():
    PrintStyle().print("Initializing framework...")

    # Suppress only request logs but keep the startup messages
    from werkzeug.serving import WSGIRequestHandler
    from werkzeug.serving import make_server

    # Add debug info for Railway deployment
    is_railway = os.environ.get("RAILWAY") == "true"
    if is_railway:
        print(f"======== STARTING AGENT9001 IN RAILWAY ENVIRONMENT ========")
        print(f"Python version: {sys.version}")
        print(f"Current working directory: {os.getcwd()}")
        print(f"Environment variables: PORT={os.environ.get('PORT')}")
        print(f"Files in current directory: {os.listdir('.')}")
        sys.stdout.flush()
    
    PrintStyle().print("Starting job loop...")
    try:
        job_loop = DeferredTask().start_task(run_loop)
        PrintStyle().print("Job loop started successfully")
    except Exception as e:
        print(f"Error starting job loop: {str(e)}")
        traceback.print_exc()

    PrintStyle().print("Starting server...")
    class NoRequestLoggingWSGIRequestHandler(WSGIRequestHandler):
        def log_request(self, code="-", size="-"):
            pass  # Override to suppress request logging

    # Get configuration from environment
    # Use Railway PORT if available or fall back to runtime port
    port = int(os.environ.get("PORT", runtime.get_web_ui_port()))
    
    # Always bind to all interfaces when in Railway environment
    is_railway = os.environ.get("RAILWAY") == "true"
    if is_railway:
        host = "0.0.0.0"
        PrintStyle().print(f"Detected Railway environment, binding to {host}:{port}")
    else:
        host = (
            runtime.get_arg("host") or dotenv.get_dotenv_value("WEB_UI_HOST") or "localhost"
        )
    
    # Disable Cloudflare tunnel in Railway environment
    use_cloudflare = not is_railway and (
        runtime.get_arg("cloudflare_tunnel")
        or dotenv.get_dotenv_value("USE_CLOUDFLARE", "false").lower()
    ) == "true"

    tunnel = None

    try:
        # Initialize and start Cloudflare tunnel if enabled
        if use_cloudflare and port:
            try:
                tunnel = CloudflareTunnel(port)
                tunnel.start()
            except Exception as e:
                PrintStyle().error(f"Failed to start Cloudflare tunnel: {e}")
                PrintStyle().print("Continuing without tunnel...")

        # initialize contexts from persisted chats
        persist_chat.load_tmp_chats()
        # # reload scheduler
        # scheduler = TaskScheduler.get()
        # asyncio.run(scheduler.reload())

    except Exception as e:
        PrintStyle().error(errors.format_error(e))

    server = None

    def register_api_handler(app, handler: type[ApiHandler]):
        name = handler.__module__.split(".")[-1]
        instance = handler(app, lock)

        if handler.requires_loopback():

            @requires_loopback
            async def handle_request():
                return await instance.handle_request(request=request)

        elif handler.requires_auth():

            @requires_auth
            async def handle_request():
                return await instance.handle_request(request=request)

        elif handler.requires_api_key():

            @requires_api_key
            async def handle_request():
                return await instance.handle_request(request=request)

        else:
            # Fallback to requires_auth
            @requires_auth
            async def handle_request():
                return await instance.handle_request(request=request)

        app.add_url_rule(
            f"/{name}",
            f"/{name}",
            handle_request,
            methods=["POST", "GET"],
        )

    # initialize and register API handlers
    handlers = load_classes_from_folder("python/api", "*.py", ApiHandler)
    for handler in handlers:
        register_api_handler(app, handler)

    try:
        # For Railway, check if running under Gunicorn
        is_gunicorn = "gunicorn" in os.environ.get("SERVER_SOFTWARE", "")
        is_railway = os.environ.get("RAILWAY") == "true"
        
        # Print server startup info
        PrintStyle().print(f"Starting server on {host}:{port}")
        
        printer = PrintStyle()
        
        def signal_handler(sig=None, frame=None):
            nonlocal tunnel, printer
            with lock:
                printer.print("Caught signal, stopping server...")
                process.stop_server()
                if tunnel:
                    tunnel.stop()
                    tunnel = None
                printer.print("Server stopped")
                sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # We're not running under Gunicorn anymore - simple Python command for Railway
        if is_railway:
            PrintStyle().print(f"Railway deployment: Running Flask app directly on {host}:{port}")
            try:
                # Use Flask's built-in server for simplicity in Railway environment
                app.run(
                    host=host,
                    port=port,
                    debug=False,
                    use_reloader=False
                )
            except Exception as e:
                print(f"ERROR STARTING FLASK APP: {str(e)}")
                traceback.print_exc()
                sys.exit(1)
        else:
            # Create and start the server for local development
            server = make_server(
                host=host,
                port=port,
                app=app,
                request_handler=NoRequestLoggingWSGIRequestHandler,
                threaded=True,
            )
            process.set_server(server)
            server.log_startup()
            server.serve_forever()
    finally:
        # Clean up tunnel if it was started
        if tunnel:
            tunnel.stop()


# Initialize core functionality regardless of how the module is imported
runtime.initialize()
dotenv.load_dotenv()

# Run the server only when directly executed
if __name__ == "__main__":
    run()
