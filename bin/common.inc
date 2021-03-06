#@IgnoreInspection BashAddShebang
#
# exports the following items:
#
# functions:
#  realpath() - resolve a path containing symlinks or .. to the real path
#  fail() - print arguments to stderr and exit with a failure code
#
# general variables:
#  MD5SUM - path to the gnu md5sum
#  repo_dir - root of the git repository
#
# django variables: (should match settings.py)
#  project_dir - root django project path
#  base_dir - django site app path
#  static_dir - collected static files path
#  frontend_dir - frontend spa javascript source path

realpath=$( command -v realpath >/dev/null 2>&1 ) || function realpath() {
    # OSX readlink does not contain the canonicalize functionality that gnu readlink does
    # so we do this in python
    python -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$1"
}

function require_virtualenv() {
	# validate that a virtualenv is active and if not, try to activate it
	if [ "$VIRTUAL_ENV" = "" ] ; then
		if [ -d .venv ] ; then
			source .venv/bin/activate
		else
			source ${WORKON_HOME:-~/.virtualenvs}/$(cat .venv)/bin/activate
		fi
	fi
}

function fail() {
	echo "$@" >&2
	exit 1
}

MD5SUM="$( which md5sum || which gmd5sum )"

# BASE_DIR and PROJECT_DIR should resolve to the same thing as in the django settings file
repo_dir="$(realpath "$(dirname "${BASH_SOURCE[0]}")/..")"

is_ci=${CI-false}

project_dir="$repo_dir/nac"
base_dir="$project_dir/newage"
static_dir="$repo_dir/assets"
frontend_dir="$repo_dir/frontend"

cd "$repo_dir"
