# Upstream Caddy carries the file capability cap_net_bind_service on /usr/bin/caddy; with `cap_drop: ALL` + no-new-privileges that makes
# exec fail ("Operation not permitted"). We listen on 8443 (unprivileged), so the capability is removed at build time.
# The explicit Alpine release tag keeps this Linux multi-arch build independent of Windows index updates.
FROM caddy:2.11.9-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0
RUN setcap -r /usr/bin/caddy && test -z "$(getcap /usr/bin/caddy)"
