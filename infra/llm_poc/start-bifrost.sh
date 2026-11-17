#!/bin/sh
# Bifrost HTTP v2.5.1: secrets live in an owner-only tmpfs config, never command arguments or exported environment.
# The relay credential is not the provider API key. The relay replaces it only after its own authorization checks.
set +x
set +a
set -eu
umask 077

fail() { printf '%s\n' 'Bifrost configuration refused' >&2; exit 1; }

render_only=false
case "$#:$*" in
    0:) ;;
    1:--render-only) render_only=true ;;
    *) fail ;;
esac

# Nonsecret paths may be overridden for isolated renderer tests. Compose fixes these to its secret/tmpfs/config mounts.
app_dir=${APP_DIR:-/app/data}
secrets_dir=${BIFROST_SECRETS_DIR:-/run/secrets}
template=${BIFROST_CONFIG_TEMPLATE:-/etc/bifrost/config.template.json}
[ -d "$app_dir" ] && [ -f "$template" ] || fail

# Unsetting first also removes inherited export attributes: even an allexport parent cannot export these values to mv/main.
unset loaded_secret admin_password virtual_key relay_auth trailing
read_secret() {
    loaded_secret=
    trailing=
    exec 3< "$secrets_dir/$1" || fail
    IFS= read -r loaded_secret <&3 || [ -n "$loaded_secret" ] || fail
    if IFS= read -r trailing <&3 || [ -n "$trailing" ]; then fail; fi
    exec 3<&-
    [ "${#loaded_secret}" -eq 64 ] || fail
    case "$loaded_secret" in *[!0123456789abcdef]*) fail ;; esac
}

read_secret bifrost_admin_password
admin_password=$loaded_secret
read_secret bifrost_virtual_key
virtual_key=$loaded_secret
read_secret llm_relay_auth
relay_auth=$loaded_secret
unset loaded_secret trailing

output="$app_dir/config.json.tmp.$$"
trap 'rm -f "$output"' EXIT
trap 'exit 1' HUP INT TERM
set -C
exec 4> "$output" || fail
set +C
seen_admin=false
seen_vk=false
seen_relay=false
# Literal placeholders also identify references to the repository secret scanner. They are never evaluated as shell code.
admin_marker='$BIFROST_ADMIN_PASSWORD'
vk_marker='$BIFROST_VIRTUAL_KEY'
relay_marker='$LLM_RELAY_AUTH'
while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
        *"$admin_marker"*)
            [ "$seen_admin" = false ] || fail
            line="${line%%"$admin_marker"*}${admin_password}${line#*"$admin_marker"}"
            seen_admin=true ;;
        *"$vk_marker"*)
            [ "$seen_vk" = false ] || fail
            line="${line%%"$vk_marker"*}${virtual_key}${line#*"$vk_marker"}"
            seen_vk=true ;;
        *"$relay_marker"*)
            [ "$seen_relay" = false ] || fail
            line="${line%%"$relay_marker"*}${relay_auth}${line#*"$relay_marker"}"
            seen_relay=true ;;
    esac
    case "$line" in *'$'*) fail ;; esac
    printf '%s\n' "$line" >&4
done < "$template"
[ "$seen_admin:$seen_vk:$seen_relay" = true:true:true ] || fail
exec 4>&-
unset admin_password virtual_key relay_auth line
mv -f "$output" "$app_dir/config.json"
trap - EXIT HUP INT TERM
if [ "$render_only" = true ]; then exit 0; fi
exec /app/main -app-dir "$app_dir" -host 0.0.0.0 -port 8080 -log-level warn -log-style json
