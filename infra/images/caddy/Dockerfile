# Upstream Caddy carries the file capability cap_net_bind_service on /usr/bin/caddy; with `cap_drop: ALL` + no-new-privileges that makes
# exec fail ("Operation not permitted"). We listen on 8443 (unprivileged), so the capability is removed at build time.
FROM caddy:2.11.9@sha256:e40b94d0a43b5ff69cb20568d73f10c70703df7b0ffc2298eb3d723cdc9d0bd1
RUN setcap -r /usr/bin/caddy && test -z "$(getcap /usr/bin/caddy)"
