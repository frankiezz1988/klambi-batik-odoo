#!/usr/bin/env bash
# Clone / update repo OCA (shallow) sesuai oca-repos.txt dan branch ODOO_VERSION.
set -euo pipefail
cd "$(dirname "$0")/.."
BRANCH="${ODOO_VERSION:-19.0}"
mkdir -p addons-oca
grep -vE '^\s*(#|$)' oca-repos.txt | while read -r repo; do
  dest="addons-oca/${repo}"
  if [ -d "${dest}/.git" ]; then
    echo ">> update ${repo}@${BRANCH}"
    git -C "${dest}" fetch --depth 1 origin "${BRANCH}"
    git -C "${dest}" checkout -q FETCH_HEAD
  else
    echo ">> clone ${repo}@${BRANCH}"
    git clone --depth 1 --branch "${BRANCH}" "https://github.com/OCA/${repo}.git" "${dest}"
  fi
done
echo "OCA addons siap di addons-oca/"
