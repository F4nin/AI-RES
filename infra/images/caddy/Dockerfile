# Upstream Caddy carries the file capability cap_net_bind_service on /usr/bin/caddy; with `cap_drop: ALL` + no-new-privileges that makes
# exec fail ("Operation not permitted"). We listen on 8443 (unprivileged), so the capability is removed at build time.
FROM caddy:2.11.9@sha256:4e2425f6009577e7c651010f16679c28f7d12df3e7b1914f941a7a3370746b3c
RUN setcap -r /usr/bin/caddy && test -z "$(getcap /usr/bin/caddy)"
