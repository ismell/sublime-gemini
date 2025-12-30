#!/usr/bin/env python3
import argparse
import glob
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request


def send_json_rpc(url, token, payload):
    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", token)
    req.add_header("Content-Type", "application/json")

    try:
        json_data = json.dumps(payload).encode("utf-8")
        with urllib.request.urlopen(req, data=json_data, timeout=10) as response:
            if response.status == 200:
                return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} {e.reason}", file=sys.stderr)
        try:
            print(e.read().decode("utf-8"), file=sys.stderr)
        except Exception:
            pass
    except Exception as e:
        print(f"Error sending request: {e}", file=sys.stderr)
    return None


def check_connection(port, token):
    """
    Tries to send an 'initialize' request to the server.
    Returns the server response (dict) if successful, None otherwise.
    """
    url = f"http://127.0.0.1:{port}/mcp"
    data = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-script", "version": "1.0"},
        },
        "id": 1,
    }

    return send_json_rpc(url, token, data)


def find_active_server():
    tmp = tempfile.gettempdir()
    # Pattern used by gemini.py: gemini-ide-server-{pid}-{port}.json
    pattern = os.path.join(tmp, "gemini", "ide", "gemini-ide-server-*.json")
    files = glob.glob(pattern)

    if not files:
        # Also check local directory for easier debugging if needed
        local_pattern = os.path.join(os.getcwd(), "gemini-ide-server-*.json")
        files = glob.glob(local_pattern)

    if not files:
        return None, None

    # Sort by modification time, newest first
    files.sort(key=os.path.getmtime, reverse=True)

    for fpath in files:
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
                port = data.get("port")
                token = data.get("authToken")

                if port and token:
                    # Try to ping
                    if check_connection(port, token):
                        return port, token
        except Exception:
            continue

    return None, None


def main():
    parser = argparse.ArgumentParser(
        description="MCP Standalone Test Client for Sublime Text Gemini Plugin"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List tools
    subparsers.add_parser("list", help="List available tools")

    # Call tool
    call_parser = subparsers.add_parser("call", help="Call a tool")
    call_parser.add_argument("name", help="Name of the tool to call")
    call_parser.add_argument(
        "args",
        help='JSON arguments for the tool (e.g. \'{"key": "value"}\')',
        default="{}",
        nargs="?",
    )
    call_parser.add_argument(
        "--arg-file",
        metavar="KEY=PATH",
        action="append",
        help="Load an argument from a file (e.g. --arg-file newContent=my_code.py)",
    )

    # Raw JSON-RPC
    raw_parser = subparsers.add_parser("raw", help="Send raw JSON-RPC method")
    raw_parser.add_argument("method", help="Method name")
    raw_parser.add_argument("params", help="JSON params", default="{}", nargs="?")

    # Connection Info
    subparsers.add_parser("info", help="Show connection info and discovery path")

    args = parser.parse_args()

    # Find Server
    port, token = find_active_server()
    if not port or not token:
        print("Error: Could not find an active Gemini IDE server.", file=sys.stderr)
        print("Ensure Sublime Text is running and the plugin is loaded.", file=sys.stderr)
        sys.exit(1)

    base_url = f"http://127.0.0.1:{port}/mcp"

    if args.command == "info":
        print(f"Connected to port: {port}")
        print(f"Token: {token}")
        print(f"Base URL: {base_url}")
        print(f"Try running: {sys.argv[0]} list")
        return

    # If no command provided, treat as 'list' if interactive, else help
    if not args.command:
        # Default to list
        args.command = "list"

    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
    }

    if args.command == "list":
        payload["method"] = "tools/list"
        payload["params"] = {}

    elif args.command == "call":
        try:
            tool_args = json.loads(args.args)
        except json.JSONDecodeError:
            print("Error: Arguments must be valid JSON.", file=sys.stderr)
            sys.exit(1)

        if args.arg_file:
            for item in args.arg_file:
                if "=" not in item:
                    print(f"Error: --arg-file expects KEY=PATH, got '{item}'", file=sys.stderr)
                    sys.exit(1)
                k, v = item.split("=", 1)
                try:
                    with open(v, "r", encoding="utf-8") as f:
                        tool_args[k] = f.read()
                except Exception as e:
                    print(f"Error reading file '{v}': {e}", file=sys.stderr)
                    sys.exit(1)

        payload["method"] = "tools/call"
        payload["params"] = {"name": args.name, "arguments": tool_args}

    elif args.command == "raw":
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError:
            print("Error: Params must be valid JSON.", file=sys.stderr)
            sys.exit(1)

        payload["method"] = args.method
        payload["params"] = params

    # Execute
    resp = send_json_rpc(base_url, token, payload)

    # Pretty print response
    if resp:
        print(json.dumps(resp, indent=2))
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
