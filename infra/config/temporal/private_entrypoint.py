"""Start one G02 private listener bound to its Compose network alias."""

import ipaddress
import os
import socket
import sys

SERVICES = {
    "platform": ("platform-api", "AI_RES_PLATFORM_LISTENER_BIND_HOST", "ai_res.api.serve_platform_v2"),
    "delivery": ("assigned-delivery", "AI_RES_ASSIGNED_DELIVERY_BIND_HOST", "ai_res.api.serve_assigned_delivery"),
}
PRIVATE_IPV4 = tuple(ipaddress.IPv4Network(block) for block in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in SERVICES:
        raise SystemExit("select one private G02 listener")
    alias, bind_setting, module = SERVICES[sys.argv[1]]
    try:
        records = socket.getaddrinfo(alias, None, socket.AF_INET, socket.SOCK_STREAM)
        addresses = {ipaddress.IPv4Address(record[4][0]) for record in records}
    except (OSError, ValueError) as error:
        raise SystemExit("private G02 listener address is unavailable") from error
    if len(addresses) != 1:
        raise SystemExit("private G02 listener requires one private IPv4 address")
    address = addresses.pop()
    if not any(address in block for block in PRIVATE_IPV4):
        raise SystemExit("private G02 listener requires one private IPv4 address")
    os.environ[bind_setting] = str(address)
    flags = ["--require-native-auth"] if sys.argv[1] == "platform" else []
    os.execv(sys.executable, [sys.executable, "-m", module, *flags])  # noqa: S606


if __name__ == "__main__":
    main()
