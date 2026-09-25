#!/usr/bin/env bash
set -u -o pipefail

INTERFACE="wlx78bdbc575d1c"
CONNECTION_UUID="f8a48888-6457-4a62-91c3-c61e0fa11c05"

# Caminho físico confirmado do adaptador Broadcom:
# /sys/devices/.../usb1/1-4/1-4.3
# IMPORTANTE: 1-4 é o hub compartilhado com armazenamento.
# O Guardião toca SOMENTE em 1-4.3.
USB_DEVICE="1-4.3"
USB_AUTH="/sys/bus/usb/devices/${USB_DEVICE}/authorized"

STATE_FILE="/run/zion-wifi-guardian.failures"
LOCK_DIR="/run/zion-wifi-guardian.lock"

USB_RESET_AFTER=3
RECONNECT_WAIT_SECONDS=8
USB_OFF_SECONDS=3
USB_REENUMERATE_SECONDS=10

log() {
    logger -t zion-wifi-guardian -- "$*"
}

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    exit 0
fi
trap cleanup EXIT

read_failures() {
    local value="0"

    if [[ -r "$STATE_FILE" ]]; then
        read -r value < "$STATE_FILE" || value="0"
    fi

    if [[ ! "$value" =~ ^[0-9]+$ ]]; then
        value="0"
    fi

    printf '%s\n' "$value"
}

write_failures() {
    printf '%s\n' "$1" > "$STATE_FILE"
    chmod 0600 "$STATE_FILE"
}

reset_failures() {
    write_failures 0
}

interface_exists() {
    [[ -d "/sys/class/net/${INTERFACE}" ]]
}

nm_state_number() {
    local state

    state="$(
        nmcli -t -g GENERAL.STATE device show "$INTERFACE" 2>/dev/null \
            | head -n 1
    )"

    printf '%s\n' "${state%% *}"
}

wifi_connected() {
    interface_exists || return 1
    [[ "$(nm_state_number)" == "100" ]]
}

bring_connection_up() {
    nmcli device set "$INTERFACE" managed yes >/dev/null 2>&1 || true

    nmcli connection up uuid "$CONNECTION_UUID" ifname "$INTERFACE" \
        >/dev/null 2>&1
}

usb_reset() {
    if [[ ! -e "$USB_AUTH" ]]; then
        log "RESET_USB_ABORTADO usb=${USB_DEVICE} motivo=authorized_ausente"
        return 1
    fi

    log "RESET_USB_INICIO usb=${USB_DEVICE} interface=${INTERFACE}"

    printf '0\n' > "$USB_AUTH" || return 1
    sleep "$USB_OFF_SECONDS"
    printf '1\n' > "$USB_AUTH" || return 1
    sleep "$USB_REENUMERATE_SECONDS"

    if ! interface_exists; then
        log "RESET_USB_FALHOU usb=${USB_DEVICE} motivo=interface_nao_retornou"
        return 1
    fi

    bring_connection_up || true
    sleep "$RECONNECT_WAIT_SECONDS"

    if wifi_connected; then
        log "RESET_USB_OK usb=${USB_DEVICE} interface=${INTERFACE}"
        return 0
    fi

    log "RESET_USB_SEM_CONEXAO usb=${USB_DEVICE} interface=${INTERFACE}"
    return 1
}

if wifi_connected; then
    reset_failures
    exit 0
fi

failures="$(read_failures)"
failures=$((failures + 1))
write_failures "$failures"

if interface_exists; then
    log "WIFI_DESCONECTADO interface=${INTERFACE} tentativa=${failures}/${USB_RESET_AFTER}"

    if bring_connection_up; then
        sleep "$RECONNECT_WAIT_SECONDS"

        if wifi_connected; then
            log "RECONEXAO_OK interface=${INTERFACE}"
            reset_failures
            exit 0
        fi
    fi
else
    log "WIFI_INTERFACE_AUSENTE interface=${INTERFACE} tentativa=${failures}/${USB_RESET_AFTER}"
fi

if (( failures < USB_RESET_AFTER )); then
    exit 0
fi

# Só após falhas consecutivas fazemos a ação forte.
# O reset é restrito ao dispositivo 1-4.3; o hub 1-4 nunca é desligado.
if usb_reset; then
    reset_failures
    exit 0
fi

# Mantemos o contador no limiar para tentar novamente no próximo ciclo,
# sem crescimento indefinido do arquivo de estado.
write_failures "$USB_RESET_AFTER"
exit 1
