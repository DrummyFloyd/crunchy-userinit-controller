#!/usr/bin/env bash

check_vars() {
  local var_unset=false
  for var_name in "$@"; do
    if [ -z "${!var_name}" ]; then
      echo "$var_name is unset."
      var_unset=true
    fi
  done
  $var_unset && exit 1
  return 0
}

check_vars CRUI_WATCH_NAMESPACE

kopf_cmd="kopf run --liveness=http://0.0.0.0:8080/healthz --namespace ${CRUI_WATCH_NAMESPACE} -m userinit.userinit"
[ "${CRUI_DEBUG}" = "true" ] && kopf_cmd+=" --verbose"

exec $kopf_cmd
