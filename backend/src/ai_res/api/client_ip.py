"""Client IP for rate limiting (Auth v1.1 §4). X-Forwarded-For is honoured ONLY when the direct peer is a configured trusted proxy (Caddy);
otherwise the header is attacker-controlled and ignored. Walking the list from the right and skipping trusted hops makes values a client
prepends useless."""
import ipaddress
from collections.abc import Sequence

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
UNKNOWN = "unknown"  # one shared bucket: a request without a usable peer is never exempt from limiting


def parse_trusted_proxies(cidrs: Sequence[str]) -> tuple[IPNetwork, ...]:
    return tuple(ipaddress.ip_network(c.strip(), strict=False) for c in cidrs)


def _parse(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def resolve_client_ip(peer: str | None, xff: str | None, trusted: Sequence[IPNetwork]) -> str:
    peer_ip = _parse(peer) if peer else None
    if peer_ip is None:
        return UNKNOWN
    if not trusted or not any(peer_ip in net for net in trusted) or xff is None:
        return str(peer_ip)
    for raw in reversed(xff.split(",")):
        hop = _parse(raw)
        if hop is None:
            return str(peer_ip)  # malformed chain: do not guess
        if not any(hop in net for net in trusted):
            return str(hop)
    return str(peer_ip)
