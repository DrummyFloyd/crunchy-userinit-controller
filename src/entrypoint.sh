#!/usr/bin/env bash
#
check_vars()
{
    var_names=("$@")
    for var_name in "${var_names[@]}"; do
        [ -z "${!var_name}" ] && echo "$var_name is unset." && var_unset=true
    done
    [ -n "$var_unset" ] && exit 1
    return 0
}

check_vars CRUI_WATCH_NAMESPACE

if [ "${CRUI_DEBUG}" = "true" ]; then
  kopf run --liveness=http://0.0.0.0:8080/healthz --namespace "${CRUI_WATCH_NAMESPACE}" userinit.py --verbose
else
  kopf run --liveness=http://0.0.0.0:8080/healthz --namespace "${CRUI_WATCH_NAMESPACE}" userinit.py
fi
