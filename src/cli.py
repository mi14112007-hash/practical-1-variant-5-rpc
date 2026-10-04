"""Command-line server, local REPL and RPC client REPL."""

import argparse
import json

from .model import DataModel, OPERATIONS


def repl(target):
    """Read JSON commands and call matching model/client methods."""
    print("Enter JSON: {\"method\": \"get_people\", \"args\": {}}")
    print("Type quit to exit.")
    while True:
        try:
            line = input("variant5> ").strip()
        except EOFError:
            return
        if line in {"quit", "exit"}:
            return
        if not line:
            continue
        try:
            command = json.loads(line)
            method = command["method"]
            if method not in OPERATIONS:
                raise ValueError("unknown method")
            args = command.get("args", {})
            if not isinstance(args, dict):
                raise ValueError("args must be an object")
            result = getattr(target, method)(**args)
            print(json.dumps(result, ensure_ascii=False))
        except (ValueError, TypeError, KeyError) as error:
            print(json.dumps({"error": str(error)}, ensure_ascii=False))


def main():
    """Select server, local REPL or remote REPL mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("server", "local", "client"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--journal", default="journal.log")
    args = parser.parse_args()
    if args.mode == "local":
        repl(DataModel())
    elif args.mode == "client":
        from .rpc import RpcClient

        repl(RpcClient(args.host, args.port))
    else:
        from .rpc import RpcServer

        with RpcServer(
            (args.host, args.port), journal_path=args.journal
        ) as server:
            print(f"RPC listening on {args.host}:{server.server_address[1]}")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("Stopped")


if __name__ == "__main__":
    main()
