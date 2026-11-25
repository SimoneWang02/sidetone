# Sourced by pre-commit and pre-push. Tests a clean copy, never the shared folder: other
# sessions' unfinished edits must not fail this commit, nor make a broken one pass.

PYTHON="${SIDETONE_PYTHON:-$HOME/.local/share/kokoro/venv/bin/python}"

# Reads file names; succeeds when every one is documentation.
only_documentation() {
    ! grep -qvE '(\.md|^LICENSE|^\.gitignore)$'
}

# run_tests quick|all DIR
run_tests() {
    local kind=$1 dir=$2 file failed=0 logs lock
    if [ ! -x "$PYTHON" ]; then
        echo "sidetone: no Python at $PYTHON, tests not run (set SIDETONE_PYTHON)" >&2
        return 1
    fi
    lock="$(git rev-parse --path-format=absolute --git-common-dir)/sidetone-check.lock"
    # One run at a time: some tests wait on real processes and fail on a crowded machine.
    exec 9>"$lock"
    flock 9
    logs="$dir.logs"
    mkdir -p "$logs"
    if [ "$kind" = quick ]; then
        # test_hub.py takes 40 of the 52 seconds; it waits for the push.
        for file in "$dir"/tests/test_*.py; do
            file=${file##*/}
            [ "$file" = test_hub.py ] && continue
            (
                clean_git_env
                cd "$dir" && "$PYTHON" -I -W ignore -m unittest discover -s tests -p "$file" \
                    </dev/null >"$logs/$file" 2>&1 9>&- || touch "$logs/$file.failed"
            ) &
        done
        wait
    else
        (
            clean_git_env
            cd "$dir" && "$PYTHON" -I -W ignore -m unittest discover -s tests \
                </dev/null >"$logs/all" 2>&1 9>&- || touch "$logs/all.failed"
        )
    fi
    for file in "$logs"/*.failed; do
        [ -e "$file" ] || continue
        failed=1
        echo "sidetone: tests failed (${file##*/})" >&2
        tail -n 40 "${file%.failed}" >&2
    done
    flock -u 9
    return $failed
}

# git tells a hook about its repository in GIT_*; a test that runs git must not act on it.
clean_git_env() {
    unset $(git rev-parse --local-env-vars)
}
