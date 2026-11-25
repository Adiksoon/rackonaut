# Track separately owned process groups. Commands must not daemonize themselves.
owned_groups=()

start_owned() {
    env --default-signal=INT,TERM setsid "$@" &
    owned_groups+=("$!")
}

stop_owned() {
    local pid signal attempt active
    for signal in INT TERM KILL; do
        active=0
        for pid in "${owned_groups[@]}"; do
            if kill -0 -- "-$pid" 2>/dev/null; then
                kill -s "$signal" -- "-$pid" 2>/dev/null || true
                active=1
            fi
        done
        (( active )) || break
        for attempt in {1..12}; do
            active=0
            for pid in "${owned_groups[@]}"; do
                if kill -0 -- "-$pid" 2>/dev/null; then active=1; fi
            done
            (( active )) || break
            sleep 0.1
        done
    done
    for pid in "${owned_groups[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
    for pid in "${owned_groups[@]}"; do
        if kill -0 -- "-$pid" 2>/dev/null; then
            printf 'Process group %s remains after cleanup.\n' "$pid" >&2
            return 1
        fi
    done
    owned_groups=()
}
