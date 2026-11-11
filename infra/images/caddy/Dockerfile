# Upstream Caddy carries the file capability cap_net_bind_service on /usr/bin/caddy; with `cap_drop: ALL` + no-new-privileges that makes
# exec fail ("Operation not permitted"). We listen on 8443 (unprivileged), so the capability is removed at build time.
FROM caddy:2.11.9@sha256:0c2243efcf437ab7f7a978f1027fcf0d4f9be8a75df27b1b3fbc5dbe0ffa8cf0
RUN setcap -r /usr/bin/caddy && test -z "$(getcap /usr/bin/caddy)"
