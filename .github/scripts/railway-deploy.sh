#!/usr/bin/env bash
# Deploys each service passed as an argument, polling Railway's own
# deployment status instead of relying on `railway up --ci`'s exit code.
#
# Why: `railway up --ci` streams build logs over a websocket and treats
# ANY failure of that stream (not the build/deploy itself) as fatal --
# confirmed in the CLI's source (railwayapp/cli src/commands/up.rs):
# `eprintln!("Failed to stream build logs: {e}"); if ci_mode { exit(1) }`.
# This is a known, still-open upstream flakiness
# (https://github.com/railwayapp/cli/issues/696) that hit this repo's
# deploy-staging job twice in a row on 2026-08-10, both times on a build
# that had actually succeeded on Railway's side.
#
# Fix: use `--detach --json` instead, which returns immediately once the
# build is queued and never touches the flaky log stream (this is also
# the CLI's own documented automation path -- see `railway up --help`'s
# "Automation notes"). Then poll `railway deployment list --json` for the
# specific deploymentId until it reaches a terminal status, and use THAT
# as the real success/failure signal.
#
# Also fixes a second, unrelated bug: the previous inline script ran all
# three `railway up` commands in one `bash -e` block, so a failure in the
# first service's command (even a spurious one, per above) silently
# skipped the other two services' deploys entirely. Every service listed
# here is always attempted regardless of an earlier one's outcome; the
# script's exit code only reflects whether any of them actually failed.
set -uo pipefail

POLL_INTERVAL_SECONDS=10
POLL_MAX_ATTEMPTS=60 # ~10 minutes per service, well above observed build times

deploy_service() {
	local service="$1"
	echo "::group::Deploying ${service}"

	local up_output
	up_output=$(npx -y @railway/cli@latest up --service "${service}" --detach --json)
	local up_exit=$?

	if [ "${up_exit}" -ne 0 ]; then
		echo "::error::${service}: railway up failed to queue the build (exit ${up_exit})"
		echo "::endgroup::"
		return 1
	fi

	local deployment_id
	deployment_id=$(printf '%s' "${up_output}" | jq -r '.deploymentId // empty')
	if [ -z "${deployment_id}" ]; then
		echo "::error::${service}: couldn't parse deploymentId from railway up output: ${up_output}"
		echo "::endgroup::"
		return 1
	fi
	echo "${service}: queued deployment ${deployment_id}, polling Railway for its real status..."

	local status="UNKNOWN"
	local attempt=0
	while [ "${attempt}" -lt "${POLL_MAX_ATTEMPTS}" ]; do
		status=$(npx -y @railway/cli@latest deployment list --service "${service}" --json --limit 10 2>/dev/null |
			jq -r --arg id "${deployment_id}" '.[] | select(.id == $id) | .status // empty')

		case "${status}" in
		SUCCESS | SKIPPED)
			echo "${service}: deployment ${deployment_id} -> ${status}"
			echo "::endgroup::"
			return 0
			;;
		FAILED | CRASHED | REMOVED)
			echo "::error::${service}: deployment ${deployment_id} -> ${status}"
			echo "::endgroup::"
			return 1
			;;
		esac

		attempt=$((attempt + 1))
		sleep "${POLL_INTERVAL_SECONDS}"
	done

	echo "::error::${service}: timed out after ~$((POLL_MAX_ATTEMPTS * POLL_INTERVAL_SECONDS / 60))m waiting for deployment ${deployment_id} (last status: ${status})"
	echo "::endgroup::"
	return 1
}

overall_exit=0
for service in "$@"; do
	deploy_service "${service}" || overall_exit=1
done

exit "${overall_exit}"
