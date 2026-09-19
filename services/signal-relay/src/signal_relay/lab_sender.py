from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import time

LAB_SESSION_FIELD = "signal_relay_session"


def main() -> None:
    import LXMF
    import RNS

    config_dir = sys.argv[1]
    payload = json.loads(sys.stdin.read())
    destination_hash = bytes.fromhex(payload["destinationHash"])
    result: dict[str, str] = {"state": "failed", "errorCode": "outbound_error", "sourceHash": ""}
    storage_dir = tempfile.mkdtemp(prefix="signal-relay-lab-")

    try:
        RNS.Reticulum(configdir=config_dir)
        RNS.Transport.request_path(destination_hash)
        for _ in range(80):
            if RNS.Transport.has_path(destination_hash):
                break
            time.sleep(0.25)
        else:
            result["errorCode"] = "path_unavailable"
            return

        destination_identity = RNS.Identity.recall(destination_hash)
        if destination_identity is None:
            result["errorCode"] = "destination_unavailable"
            return

        source_identity = RNS.Identity()
        source = RNS.Destination(source_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        destination = RNS.Destination(destination_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        router = LXMF.LXMRouter(identity=source_identity, storagepath=storage_dir)
        message = LXMF.LXMessage(
            destination,
            source,
            payload["content"],
            fields={LAB_SESSION_FIELD: payload["sessionId"]},
        )
        completed = threading.Event()
        result["sourceHash"] = RNS.hexrep(source.hash, delimit=False)
        message.register_delivery_callback(lambda _: (result.update(state="delivered", errorCode=""), completed.set()))
        message.register_failed_callback(lambda _: (result.update(state="failed", errorCode="delivery_failed"), completed.set()))
        router.handle_outbound(message)
        if not completed.wait(60):
            result["errorCode"] = "delivery_timeout"
    except Exception:
        result["errorCode"] = "outbound_error"
    finally:
        print(json.dumps(result), flush=True)
        shutil.rmtree(storage_dir, ignore_errors=True)


if __name__ == "__main__":
    main()