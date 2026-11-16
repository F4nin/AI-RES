# Upstream Caddy carries the file capability cap_net_bind_service on /usr/bin/caddy; with `cap_drop: ALL` + no-new-privileges that makes
# exec fail ("Operation not permitted"). We listen on 8443 (unprivileged), so the capability is removed at build time.
FROM caddy:2.11.9@sha256:f971688b2aaf1a26d256de552f17fb13f64fc5ed2dee4cf40c7f9d70cea0e12d
RUN setcap -r /usr/bin/caddy && test -z "$(getcap /usr/bin/caddy)"
