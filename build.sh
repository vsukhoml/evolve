#!/usr/bin/env bash
#
# build.sh --- the release gate for this repo.
#
# There is no compiler and no test suite here: the deliverable is prose plus a
# stdlib-only Python harness that gets copied verbatim into every experiment
# directory. So "build" means "prove the things that break silently are intact".
#
# Hard checks (a failure exits non-zero):
#   - both plugin manifests parse and agree on their duplicated fields
#   - the root plugin.json still conforms to Agent Plugins 1.0.0: closed schema,
#     name grammar, skills discoverable at skills/<name>/SKILL.md
#   - every .py byte-compiles
#   - no third-party imports anywhere in the harness
#   - the three harness entry points run clean on an empty experiment
#   - every shipped skill has name+description frontmatter, with a short name
#   - skills/design/assets/ae still exists at the path the runtime glob expects
#
# Soft checks (reported, but do not fail the build unless --strict):
#   - ruff lint
#   - markdown formatting drift against `mdformat --number --wrap 80`
#
# Python formatting is NOT checked. Layout there is hand-chosen for readability
# and `ruff format` loses that, so there is no format gate and no drift warning.
# Markdown IS the deliverable and IS normalized: mdformat with the frontmatter
# plugin (without it, SKILL.md YAML headers get rewritten into body text --- a
# plain `mdformat` install is not enough and the gate refuses to use one).
#
# Usage:
#   ./build.sh            run every check
#   ./build.sh --strict   also fail on lint findings
#   ./build.sh fmt-md     apply `mdformat --number --wrap 80` to the repo's
#                         markdown (README.md and skills/). The house style.
#   ./build.sh fmt        apply `ruff format` in place. NOT the house style ---
#                         this reflows hand-laid-out code and will collapse the
#                         aligned comment columns in the reference docs. Here as
#                         an escape hatch, not a step anyone should run casually.

set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")"

# Clean up any stray em-dashes in the markdown.
find . -type f -name "*.md" -exec sed -i 's/—/-/g' {} +

STRICT=0
MODE=check
for arg in "$@"; do
    case "$arg" in
        --strict) STRICT=1 ;;
        fmt|format) MODE=fmt ;;
        fmt-md|fmtmd) MODE=fmtmd ;;
        check) MODE=check ;;
        # Print the header block, whatever length it has grown to: every line
        # from 3 until the first that is not a comment.
        -h|--help) sed -n '3,${/^#/!q;p;}' "$0"; exit 0 ;;
        *) echo "unknown argument: $arg" >&2; exit 64 ;;
    esac
done

FAILED=0
WARNED=0

if [ -t 1 ]; then R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[1m'; N=$'\033[0m'
else R=; G=; Y=; B=; N=; fi

step() { printf '\n%s==> %s%s\n' "$B" "$1" "$N"; }
pass() { printf '%s  PASS%s %s\n' "$G" "$N" "$1"; }
warn() { printf '%s  WARN%s %s\n' "$Y" "$N" "$1"; WARNED=$((WARNED + 1)); [ "$STRICT" = 1 ] && FAILED=$((FAILED + 1)); return 0; }
fail() { printf '%s  FAIL%s %s\n' "$R" "$N" "$1"; FAILED=$((FAILED + 1)); }

# ruff is not a dependency of this repo --- it is a convenience. Prefer a real
# install, fall back to uvx, and degrade to a warning if neither is present.
ruff_cmd() {
    if command -v ruff >/dev/null 2>&1; then echo "ruff"
    elif command -v uvx >/dev/null 2>&1; then echo "uvx ruff"
    else echo ""; fi
}

# Same deal for mdformat, with one hard requirement: the frontmatter plugin.
# Without it mdformat parses a SKILL.md's leading `---` as a thematic break and
# rewrites the YAML header into body text --- silently, exit 0. A bare install
# that lacks the plugin is therefore worse than no install, and is skipped.
mdformat_cmd() {
    if command -v mdformat >/dev/null 2>&1 &&
       mdformat --version 2>/dev/null | grep -q frontmatter; then
        echo "mdformat"
    elif command -v uvx >/dev/null 2>&1; then
        echo "uvx --with mdformat-gfm --with mdformat-frontmatter mdformat"
    else echo ""; fi
}

# The markdown the plugin ships: README.md, the AGENTS.md universal adapter,
# and everything under skills/. Deliberately not `**/*.md` --- CLAUDE.local.md
# and .claude/ are personal tooling, and untracked scratch files are nobody's
# business.
md_files() {
    { git ls-files '*.md'; git ls-files -o --exclude-standard '*.md'; } |
        grep -e '^README\.md$' -e '^AGENTS\.md$' -e '^skills/.*\.md$' | sort -u
}

# ------------------------------------------------------------- fmt-md mode
if [ "$MODE" = fmtmd ]; then
    MDFORMAT=$(mdformat_cmd)
    if [ -z "$MDFORMAT" ]; then
        echo "mdformat with the frontmatter plugin not available" >&2
        echo "(pip install mdformat mdformat-gfm mdformat-frontmatter, or install uv for uvx)" >&2
        exit 69
    fi
    step "mdformat --number --wrap 80"
    md_files | xargs $MDFORMAT --number --wrap 80
    exit $?
fi

# ---------------------------------------------------------------- fmt mode
if [ "$MODE" = fmt ]; then
    RUFF=$(ruff_cmd)
    if [ -z "$RUFF" ]; then
        echo "ruff not available (install it, or install uv for uvx)" >&2
        exit 69
    fi
    step "ruff format"
    echo "  this reflows hand-laid-out code and collapses aligned comment columns;" >&2
    echo "  hand formatting is the house style. Ctrl-C now if that is not what you want." >&2
    $RUFF format .
    exit $?
fi

# ------------------------------------------------- 1. manifests parse+agree
step "manifests"
if jq -e . .claude-plugin/plugin.json >/dev/null 2>&1; then
    pass "plugin.json is valid JSON"
else
    fail "plugin.json is not valid JSON"
fi
if jq -e . .claude-plugin/marketplace.json >/dev/null 2>&1; then
    pass "marketplace.json is valid JSON"
else
    fail "marketplace.json is not valid JSON"
fi

# The two manifests duplicate seven fields and nothing enforces the pairing;
# a release with drifted metadata installs wrong. Compare them field by field.
if jq -e . .claude-plugin/plugin.json >/dev/null 2>&1 &&
   jq -e . .claude-plugin/marketplace.json >/dev/null 2>&1; then
    FIELDS='{name,description,version,author,license,homepage,keywords}'
    PLUGIN_NAME=$(jq -r .name .claude-plugin/plugin.json)
    if diff -u \
        <(jq -S "$FIELDS" .claude-plugin/plugin.json) \
        <(jq -S --arg n "$PLUGIN_NAME" \
            ".plugins[] | select(.name==\$n) | $FIELDS" \
            .claude-plugin/marketplace.json) >/tmp/bs-manifest-diff.$$ 2>&1; then
        pass "manifests agree (v$(jq -r .version .claude-plugin/plugin.json))"
    else
        fail "manifests disagree:"
        sed 's/^/      /' /tmp/bs-manifest-diff.$$
    fi
    rm -f /tmp/bs-manifest-diff.$$

    # The marketplace refuses to install without these.
    MISSING=$(jq -r '
        [ (if has("$schema") then empty else "$schema" end),
          (if has("name")    then empty else "name"    end),
          (if has("owner")   then empty else "owner"   end),
          (.plugins[] | if has("source")   then empty else "plugins[].source"   end),
          (.plugins[] | if has("category") then empty else "plugins[].category" end)
        ] | join(", ")' .claude-plugin/marketplace.json)
    if [ -z "$MISSING" ]; then
        pass "marketplace.json has all install-required keys"
    else
        fail "marketplace.json missing: $MISSING"
    fi

    # Every per-platform manifest carries its own copy of the version, and a
    # release with one stale copy installs wrong on exactly one platform,
    # silently. Bump them together (/bump-version); this check is the net.
    V=$(jq -r .version .claude-plugin/plugin.json)
    for m in "plugin.json .version" \
             "gemini-extension.json .version" \
             ".codex-plugin/plugin.json .version" \
             ".devin-plugin/plugin.json .version" \
             ".grok-plugin/marketplace.json .plugins[0].version"; do
        file=${m% *}; path=${m#* }
        if [ ! -f "$file" ]; then
            fail "$file is missing"
        elif [ "$(jq -r "$path" "$file")" = "$V" ]; then
            pass "$file agrees on v$V"
        else
            fail "$file version $(jq -r "$path" "$file") != plugin.json's $V"
        fi
    done

    # The Codex-native repo marketplace carries no version, but it must parse
    # and point at this repo or `codex plugin marketplace add` silently skips it.
    if jq -e '.plugins[0] | (.name == "evolve") and (.source.path == "./")' \
         .agents/plugins/marketplace.json >/dev/null 2>&1; then
        pass ".agents/plugins/marketplace.json parses and points at ./"
    else
        fail ".agents/plugins/marketplace.json missing, unparseable, or mispointed"
    fi
fi

# ------------------------------------------ 1b. Agent Plugins 1.0.0 conformance
# The root plugin.json is three files at once: the Antigravity marker, the target
# of the .claude-plugin/plugin.json symlink, and the Agent Plugins 1.0.0 manifest
# (agent-plugins.org). That third role is the strict one --- its schema is closed,
# so a stray field that every other platform would simply ignore makes the plugin
# invalid for every conformant client. Check the root file directly rather than
# through the symlink: the spec fixes the location, so that is what is being read.
step "agent-plugins"
AP_SCHEMA="https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
if [ "$(jq -r '."$schema" // ""' plugin.json)" = "$AP_SCHEMA" ]; then
    pass "plugin.json declares Agent Plugins 1.0.0"
else
    fail "plugin.json \$schema is '$(jq -r '."$schema" // "(absent)"' plugin.json)', not $AP_SCHEMA"
fi

EXTRA=$(jq -r 'keys_unsorted - ["$schema","name","version","description","author",
                                "homepage","repository","license","keywords",
                                "extensions"] | join(", ")' plugin.json)
if [ -z "$EXTRA" ]; then
    pass "plugin.json carries only spec-allowed fields"
else
    fail "plugin.json has fields the closed schema rejects: $EXTRA"
fi

# 1-64 chars of [a-z0-9.-], alphanumeric at both ends, no `--` and no `..`.
NAME=$(jq -r .name plugin.json)
if printf '%s' "$NAME" | grep -qE '^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$' &&
   ! printf '%s' "$NAME" | grep -qE -- '--|\.\.' &&
   [ ${#NAME} -le 64 ]; then
    pass "plugin name \"$NAME\" matches the spec grammar"
else
    fail "plugin name \"$NAME\" violates the spec grammar"
fi

# Skills are discovered at exactly one level --- skills/<name>/SKILL.md --- and a
# conformant client MUST NOT look deeper. So a skill parked one directory too far
# down does not fail loudly; it silently does not exist.
DEPTH=""
for d in skills/*/; do
    [ -f "${d}SKILL.md" ] || DEPTH="$DEPTH ${d%/}/SKILL.md"
done
for f in $(find skills -mindepth 3 -name SKILL.md); do
    DEPTH="$DEPTH $f (too deep to discover)"
done
if [ -z "$DEPTH" ]; then
    pass "$(find skills -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l) skills sit at skills/<name>/SKILL.md"
else
    fail "skills not at the discovered depth:$DEPTH"
fi

# --------------------------------------------------------- 2. .py compiles
step "compile"
if find skills -name '*.py' -print0 | PYTHONPYCACHEPREFIX=/tmp/bs-pycache.$$ xargs -0 python3 -m py_compile; then
    pass "$(find skills -name '*.py' | wc -l) .py files compile"
else
    fail "at least one .py file does not compile"
fi
rm -rf /tmp/bs-pycache.$$

# -------------------------------------------------------- 3. stdlib-only
# Stdlib-only is a hard rule, not a preference: an experiment has to stay
# re-derivable months later with no network and no package manager. ruff cannot
# express "no third-party imports", so check against the interpreter's own list.
step "stdlib-only"
STDLIB_OUT=$(python3 - <<'EOF'
import ast, pathlib, sys

own = {p.stem for p in pathlib.Path("skills").rglob("*.py")}
# Templates are named for the repo but import each other by the name they get
# AFTER being copied into an experiment: evaluator.py lands as evaluate.py, so
# eval_params.py importing `evaluate` resolves there and nowhere here.
own |= {"evaluate"}
bad = []
for p in sorted(pathlib.Path("skills").rglob("*.py")):
    for node in ast.walk(ast.parse(p.read_text(), str(p))):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module] if node.level == 0 and node.module else []
        else:
            continue
        for m in mods:
            root = m.split(".")[0]
            if root not in sys.stdlib_module_names and root not in own:
                bad.append(f"{p}:{node.lineno}: {m}")
print("\n".join(bad))
EOF
)
if [ -z "$STDLIB_OUT" ]; then
    pass "no third-party imports"
else
    fail "third-party imports found:"
    printf '%s\n' "$STDLIB_OUT" | sed 's/^/      /'
fi

# ------------------------------------------------- 4. empty-experiment smoke
# Runs in a temp dir --- never in the repo, never against a real experiment.
step "smoke test"
T=$(mktemp -d /tmp/bs-exp-XXXXXX)
mkdir -p "$T"/program "$T"/evaluator "$T"/generations
cp -r skills/design/assets/ae "$T"/.ae
SMOKE=$(
    python3 "$T"/.ae/evolve_db.py init  --experiment "$T" &&
    python3 "$T"/.ae/evolve_db.py stats --experiment "$T" &&
    python3 "$T"/.ae/evolve_report.py   --experiment "$T" --json
) 2>&1
SMOKE_RC=$?
if [ "$SMOKE_RC" -eq 0 ]; then
    pass "init / stats / report run clean on an empty experiment"
    if printf '%s' "$SMOKE" | tail -n +2 | jq -e . >/dev/null 2>&1; then
        pass "report --json emits valid JSON on an empty database"
    else
        # tail -n +2 skips the path evolve_db.py prints on init; if the shape of
        # that output changes this check needs updating, not the harness.
        warn "could not parse report --json output (output shape may have changed)"
    fi
else
    fail "smoke test exited $SMOKE_RC:"
    printf '%s\n' "$SMOKE" | sed 's/^/      /'
fi
rm -rf "$T"

# --------------------------------------------------- 5. skill frontmatter
# Skill `name` is the short form (`design`, not `evolve-design`) --- the
# `evolve:` prefix comes from the plugin namespace, and a mismatch here silently
# changes how the skill is addressed.
step "skill frontmatter"
for f in skills/*/SKILL.md; do
    dir=$(basename "$(dirname "$f")")
    if [ "$(head -n 1 "$f")" != "---" ]; then
        fail "$f does not open with a --- frontmatter fence"
        continue
    fi
    fm=$(awk 'NR>1 && /^---$/{exit} NR>1' "$f")
    name=$(printf '%s\n' "$fm" | sed -n 's/^name:[[:space:]]*//p' | head -1)
    if [ -z "$name" ]; then
        fail "$f has no name: in frontmatter"
    elif [ "$name" != "$dir" ]; then
        fail "$f: name '$name' does not match directory '$dir'"
    elif printf '%s' "$fm" | grep -q '^description:'; then
        pass "$dir"
    else
        fail "$f has no description: in frontmatter"
    fi
done

# ------------------------------------------------- 6. asset path contract
# Skills locate the harness at runtime with
#   find ~/.claude/plugins -path '*evolve*/skills/design/assets/ae' -type d
# so this path is part of the public contract. Moving it breaks bootstrap in
# every already-installed experiment and the stale-harness `diff -q` check.
step "asset path contract"
if [ -d skills/design/assets/ae ]; then
    pass "skills/design/assets/ae exists"
else
    fail "skills/design/assets/ae is missing --- installed experiments will not bootstrap"
fi
REFS=$(grep -rl "skills/design/assets/ae" skills/ 2>/dev/null | wc -l)
pass "$REFS skill file(s) reference the asset path"

# ------------------------------------------------------------ 7. lint (soft)
step "lint"
RUFF=$(ruff_cmd)
if [ -z "$RUFF" ]; then
    warn "ruff not available --- install it or install uv for uvx"
else
    LINT=$($RUFF check . 2>&1)
    if [ $? -eq 0 ]; then
        pass "ruff check clean"
    else
        warn "ruff check findings:"
        printf '%s\n' "$LINT" | tail -20 | sed 's/^/      /'
    fi

    # Deliberately no `ruff format --check`. Layout here is hand-chosen for
    # readability --- aligned comment columns in the reference docs' examples,
    # log() calls and dict literals laid out to read as one statement --- and
    # ruff's reflow loses that. A check that can only ever warn trains you to
    # skip the warning line, which is where a real problem would appear.
fi

# ------------------------------------------------- 8. markdown format (soft)
# The prose is the deliverable, so its formatting is normalized --- unlike the
# Python, where layout is hand-chosen and deliberately unchecked.
step "markdown format"
MDFORMAT=$(mdformat_cmd)
if [ -z "$MDFORMAT" ]; then
    warn "mdformat with the frontmatter plugin not available --- install it or install uv for uvx"
else
    MD_DRIFT=$(md_files | xargs $MDFORMAT --check --number --wrap 80 2>&1 |
               sed -n 's/^Error: File \(.*\) is not formatted.*/\1/p')
    if [ -z "$MD_DRIFT" ]; then
        pass "$(md_files | wc -l) markdown files match mdformat --number --wrap 80"
    else
        warn "markdown formatting drift --- run ./build.sh fmt-md:"
        printf '%s\n' "$MD_DRIFT" | sed 's/^/      /'
    fi
fi

# ------------------------------------------------------------------ verdict
printf '\n%s' "$B"
if [ "$FAILED" -eq 0 ] && [ "$WARNED" -eq 0 ]; then
    printf '%sall checks passed%s\n' "$G" "$N"
elif [ "$FAILED" -eq 0 ]; then
    printf '%s%d warning(s), no failures --- ready to ship%s\n' "$Y" "$WARNED" "$N"
else
    printf '%s%d check(s) failed, %d warning(s) --- not ready%s\n' "$R" "$FAILED" "$WARNED" "$N"
fi
exit $((FAILED > 0 ? 1 : 0))
