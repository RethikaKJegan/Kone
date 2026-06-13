#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-$HOME/Downloads/Kone/Kone}"
HF_TOKEN="${HF_TOKEN:}"

BACKEND_PORT="${BACKEND_PORT:-8001}"
API_PORT="${API_PORT:-4000}"
UI_PORT="${UI_PORT:-3000}"

VENV_DIR="$ROOT_DIR/.venv"
PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}"

LOG_DIR="$ROOT_DIR/setup_logs"
LOG_FILE="$LOG_DIR/setup_kone_all.log"

CACHE_DIR="$ROOT_DIR/.cache"
HF_HOME="$ROOT_DIR/.hf_home"
HUGGINGFACE_HUB_CACHE="$ROOT_DIR/.hf_home/hub"
TRANSFORMERS_CACHE="$ROOT_DIR/.hf_home/hub"
HF_HUB_CACHE="$ROOT_DIR/.hf_home/hub"
TORCH_HOME="$ROOT_DIR/.cache/torch"
XDG_CACHE_HOME="$ROOT_DIR/.cache"
PIP_CACHE_DIR="$ROOT_DIR/.cache/pip"
NPM_CONFIG_CACHE="$ROOT_DIR/.cache/npm"
MPLCONFIGDIR="$ROOT_DIR/.cache/matplotlib"
HF_HUB_DISABLE_SYMLINKS_WARNING="1"
HF_HUB_ENABLE_HF_TRANSFER="0"

PIPELINE_DIR="$ROOT_DIR/elevator_mod_pipeline"
API_DIR="$ROOT_DIR/Frontend/kone-api-master"
UI_DIR="$ROOT_DIR/Frontend/kone-ui-master"

GDINO_DIR="$ROOT_DIR/GroundingDINO"
SAM2_DIR="$ROOT_DIR/sam2_src"
LAMA_DIR="$ROOT_DIR/lama"
BERT_DIR="$ROOT_DIR/bert-base-uncased"
WEIGHTS_DIR="$ROOT_DIR/weights"
BIG_LAMA_DIR="$ROOT_DIR/big-lama"
PIPELINE_LAMA_DIR="$PIPELINE_DIR/third_party/lama/big-lama"

DINO_WEIGHT="$WEIGHTS_DIR/groundingdino_swint_ogc.pth"
SAM2_WEIGHT="$WEIGHTS_DIR/sam2.1_hiera_large.pt"
BIG_LAMA_CKPT="$BIG_LAMA_DIR/models/best.ckpt"

export ROOT_DIR HF_TOKEN BACKEND_PORT API_PORT UI_PORT VENV_DIR PY PIP TORCH_INDEX_URL
export LOG_DIR LOG_FILE CACHE_DIR HF_HOME HUGGINGFACE_HUB_CACHE TRANSFORMERS_CACHE HF_HUB_CACHE
export TORCH_HOME XDG_CACHE_HOME PIP_CACHE_DIR NPM_CONFIG_CACHE MPLCONFIGDIR
export HF_HUB_DISABLE_SYMLINKS_WARNING HF_HUB_ENABLE_HF_TRANSFER
export PIPELINE_DIR API_DIR UI_DIR GDINO_DIR SAM2_DIR LAMA_DIR BERT_DIR WEIGHTS_DIR
export BIG_LAMA_DIR PIPELINE_LAMA_DIR DINO_WEIGHT SAM2_WEIGHT BIG_LAMA_CKPT

log() {
    local message="$1"
    local stamp
    stamp="$(date '+%Y-%m-%d %H:%M:%S')"
    printf '[%s] %s\n' "$stamp" "$message"
    printf '[%s] %s\n' "$stamp" "$message" >>"$LOG_FILE"
}

fail() {
    local message="$1"
    printf '\nERROR: %s\n' "$message" >&2
    printf 'ERROR: %s\n' "$message" >>"$LOG_FILE"
    printf '\nCheck log:\n%s\n\n' "$LOG_FILE" >&2
    exit 1
}

require_cmd() {
    local name="$1"
    command -v "$name" >/dev/null 2>&1 || fail "Missing required command: $name"
    log "Found required command: $name"
}

check_optional() {
    local name="$1"
    if command -v "$name" >/dev/null 2>&1; then
        log "Found optional command: $name"
    else
        log "WARNING: Optional command not found: $name"
    fi
}

check_file() {
    local path="$1"
    [[ -f "$path" ]] && log "OK file: $path" || fail "Missing file: $path"
}

check_dir() {
    local path="$1"
    [[ -d "$path" ]] && log "OK dir: $path" || fail "Missing dir: $path"
}

find_python() {
    if [[ -n "${PY_BASE:-}" ]]; then
        command -v "$PY_BASE" >/dev/null 2>&1 || fail "PY_BASE command not found: $PY_BASE"
        printf '%s\n' "$PY_BASE"
        return 0
    fi

    for candidate in python3.13 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    fail "Missing required command: python3.13, python3, or python"
}

activate_venv() {
    [[ -f "$VENV_DIR/bin/activate" ]] || fail "Missing venv activation file: $VENV_DIR/bin/activate"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
}

configure_backend_env() {
    export PYTHONPATH="$PIPELINE_DIR/src:$ROOT_DIR:$GDINO_DIR:$SAM2_DIR:$LAMA_DIR"
    export HF_HOME HUGGINGFACE_HUB_CACHE TRANSFORMERS_CACHE HF_HUB_CACHE
    export TORCH_HOME XDG_CACHE_HOME MPLCONFIGDIR TORCH_INDEX_URL
}

create_dirs() {
    [[ -d "$ROOT_DIR" ]] || {
        printf 'ERROR: ROOT_DIR does not exist: %s\n' "$ROOT_DIR" >&2
        exit 1
    }

    mkdir -p "$LOG_DIR" "$CACHE_DIR" "$HF_HOME" "$HUGGINGFACE_HUB_CACHE"
    mkdir -p "$TORCH_HOME" "$PIP_CACHE_DIR" "$NPM_CONFIG_CACHE" "$MPLCONFIGDIR" "$WEIGHTS_DIR"
}

create_venv() {
    if [[ -x "$PY" ]]; then
        log "Python venv already exists: $VENV_DIR"
        "$PY" --version >>"$LOG_FILE" 2>&1 || fail "Venv Python check failed"
        return 0
    fi

    local python_base
    python_base="$(find_python)"
    log "Creating Python venv: $VENV_DIR"
    "$python_base" -m venv "$VENV_DIR" >>"$LOG_FILE" 2>&1 || fail "Failed to create Python venv"
    "$PY" --version >>"$LOG_FILE" 2>&1 || fail "Venv Python check failed"
}

upgrade_pip() {
    log "Upgrading pip/setuptools/wheel"
    "$PY" -m ensurepip --upgrade >>"$LOG_FILE" 2>&1 || fail "ensurepip failed"
    "$PY" -m pip install --cache-dir "$PIP_CACHE_DIR" --upgrade pip setuptools wheel >>"$LOG_FILE" 2>&1 || fail "pip upgrade failed"
}

clone_or_pull() {
    local name="$1"
    local url="$2"
    local dir="$3"

    if [[ ! -d "$dir/.git" ]]; then
        if [[ -d "$dir" ]]; then
            log "$name dir exists without .git; keeping existing dir"
        else
            git clone "$url" "$dir" >>"$LOG_FILE" 2>&1 || fail "$name clone failed"
        fi
    else
        (cd "$dir" && git pull >>"$LOG_FILE" 2>&1) || fail "$name git pull failed"
    fi
}

clone_repos() {
    log "Cloning/updating AI repos"
    clone_or_pull "GroundingDINO" "https://github.com/IDEA-Research/GroundingDINO.git" "$GDINO_DIR"
    clone_or_pull "SAM2" "https://github.com/facebookresearch/sam2.git" "$SAM2_DIR"
    clone_or_pull "LaMa" "https://github.com/advimman/lama.git" "$LAMA_DIR"
    cd "$ROOT_DIR" || fail "Cannot return to ROOT_DIR"
}

install_python_requirements() {
    log "Installing Python 3.13-compatible Torch stack"
    "$PIP" install --cache-dir "$PIP_CACHE_DIR" --index-url "$TORCH_INDEX_URL" "torch>=2.7" "torchvision>=0.22" "torchaudio>=2.7" >>"$LOG_FILE" 2>&1 || fail "Failed installing Torch stack"

    log "Installing project-side backend requirements"
    if [[ -f "$PIPELINE_DIR/requirements.txt" ]]; then
        "$PIP" install --cache-dir "$PIP_CACHE_DIR" -r "$PIPELINE_DIR/requirements.txt" >>"$LOG_FILE" 2>&1 || fail "Failed installing elevator_mod_pipeline requirements.txt"
    else
        fail "Missing project requirements: $PIPELINE_DIR/requirements.txt"
    fi

    log "Installing backend extras"
    "$PIP" install --cache-dir "$PIP_CACHE_DIR" psutil imageio-ffmpeg opencv-python pillow numpy scipy pyyaml requests tqdm uvicorn fastapi python-multipart >>"$LOG_FILE" 2>&1 || fail "Failed installing backend extras"

    log "Ensuring Python 3.13-compatible Hugging Face stack"
    "$PIP" install --cache-dir "$PIP_CACHE_DIR" --upgrade "transformers>=4.45,<5" "tokenizers>=0.20" "huggingface_hub[cli]>=0.25" >>"$LOG_FILE" 2>&1 || fail "Failed installing transformers/tokenizers/huggingface_hub"

    log "Installing API npm packages"
    if [[ -f "$API_DIR/package.json" ]]; then
        (cd "$API_DIR" && npm install --ignore-scripts --cache "$NPM_CONFIG_CACHE" >>"$LOG_FILE" 2>&1) || fail "API npm install failed"
    else
        fail "Missing API package.json"
    fi

    log "Installing UI npm packages"
    if [[ -f "$UI_DIR/package.json" ]]; then
        (cd "$UI_DIR" && npm install --ignore-scripts --cache "$NPM_CONFIG_CACHE" >>"$LOG_FILE" 2>&1) || fail "UI npm install failed"
    else
        fail "Missing UI package.json"
    fi

    cd "$ROOT_DIR" || fail "Cannot return to ROOT_DIR"
}

install_ai_repos() {
    log "Installing third-party AI repo requirements"
    log "Skipping GroundingDINO requirements.txt to avoid Python 3.13 dependency downgrades"
    log "Installing LaMa-compatible deps for Python 3.13"

    "$PIP" install --cache-dir "$PIP_CACHE_DIR" "numpy>=1.26,<2" scipy joblib threadpoolctl cython wheel setuptools "scikit-image>=0.24,<0.26" "scikit-learn>=1.5" "pytorch-lightning>=2.5,<3" "kornia>=0.7.4,<0.9" "albumentations>=2.0,<3" omegaconf==2.3.0 hydra-core==1.3.2 antlr4-python3-runtime==4.9.3 einops webdataset easydict >>"$LOG_FILE" 2>&1 || fail "Failed installing Python 3.13 LaMa deps"

    log "Ensuring torch is installed before GroundingDINO editable build"
    "$PY" -m pip install --cache-dir "$PIP_CACHE_DIR" --index-url "$TORCH_INDEX_URL" "torch>=2.7" "torchvision>=0.22" "torchaudio>=2.7" >>"$LOG_FILE" 2>&1 || fail "Torch install before GroundingDINO failed"

    log "Editable installing GroundingDINO"
    "$PY" -m pip install --cache-dir "$PIP_CACHE_DIR" --no-build-isolation -e "$GDINO_DIR" >>"$LOG_FILE" 2>&1 || fail "GroundingDINO editable install failed"

    "$PIP" install --cache-dir "$PIP_CACHE_DIR" --upgrade "transformers>=4.45,<5" "tokenizers>=0.20" "huggingface_hub[cli]>=0.25" >>"$LOG_FILE" 2>&1 || fail "Failed restoring Python 3.13-compatible Hugging Face stack after GroundingDINO"

    log "Editable installing SAM2"
    "$PIP" install --cache-dir "$PIP_CACHE_DIR" -e "$SAM2_DIR" >>"$LOG_FILE" 2>&1 || fail "SAM2 editable install failed"
}

download_models() {
    log "Preparing model/cache downloads under ROOT_DIR"

    if [[ "${HF_TOKEN,,}" != "put_your_hf_token_here" ]]; then
        export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"
        log "HF_TOKEN provided"
    else
        log "HF_TOKEN not set; public downloads will be attempted without login"
    fi

    download_bert
    download_groundingdino_weight
    download_sam2_weight
    download_big_lama
}

download_bert() {
    log "Checking bert-base-uncased"

    if [[ -f "$BERT_DIR/config.json" ]]; then
        log "BERT already exists: $BERT_DIR"
        return 0
    fi

    log "Downloading bert-base-uncased into $BERT_DIR"
    if ! "$PY" - <<'PY' >>"$LOG_FILE" 2>&1
import os
from huggingface_hub import snapshot_download

token = os.environ.get("HF_TOKEN")
if token == "PUT_YOUR_HF_TOKEN_HERE":
    token = None

snapshot_download(
    repo_id="google-bert/bert-base-uncased",
    local_dir=os.environ["BERT_DIR"],
    local_dir_use_symlinks=False,
    token=token,
)
PY
    then
        fail "bert-base-uncased download failed"
    fi
}

download_groundingdino_weight() {
    log "Checking GroundingDINO SwinT weight"

    if [[ -f "$DINO_WEIGHT" ]]; then
        log "GroundingDINO weight already exists: $DINO_WEIGHT"
        return 0
    fi

    log "Downloading GroundingDINO weight into $DINO_WEIGHT"
    curl -L --fail -o "$DINO_WEIGHT" "https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth" >>"$LOG_FILE" 2>&1 || fail "GroundingDINO weight download failed"
}

download_sam2_weight() {
    log "Checking SAM2.1 Hiera Large weight"

    if [[ -f "$SAM2_WEIGHT" ]]; then
        log "SAM2 weight already exists: $SAM2_WEIGHT"
        return 0
    fi

    log "Downloading SAM2.1 Hiera Large weight into $WEIGHTS_DIR"
    if ! "$PY" - <<'PY' >>"$LOG_FILE" 2>&1
import os
from huggingface_hub import hf_hub_download

token = os.environ.get("HF_TOKEN")
if token == "PUT_YOUR_HF_TOKEN_HERE":
    token = None

hf_hub_download(
    repo_id="facebook/sam2.1-hiera-large",
    filename="sam2.1_hiera_large.pt",
    local_dir=os.environ["WEIGHTS_DIR"],
    token=token,
)
PY
    then
        log "HF SAM2 download failed; trying SAM2 checkpoint script with bash"
        command -v bash >/dev/null 2>&1 || fail "SAM2 weight download failed and bash is unavailable"
        (cd "$SAM2_DIR/checkpoints" && bash download_ckpts.sh >>"$LOG_FILE" 2>&1) || fail "SAM2 download_ckpts.sh failed"
        if [[ -f "$SAM2_DIR/checkpoints/sam2.1_hiera_large.pt" ]]; then
            cp -f "$SAM2_DIR/checkpoints/sam2.1_hiera_large.pt" "$SAM2_WEIGHT" >>"$LOG_FILE" 2>&1 || fail "Failed copying SAM2 checkpoint"
        fi
    fi

    [[ -f "$SAM2_WEIGHT" ]] || fail "SAM2 weight missing after download"
    cd "$ROOT_DIR" || fail "Cannot return to ROOT_DIR"
}

download_big_lama() {
    log "Checking Big-LaMa checkpoint"

    if [[ -f "$BIG_LAMA_CKPT" ]]; then
        log "Big-LaMa checkpoint already exists: $BIG_LAMA_CKPT"
        return 0
    fi

    mkdir -p "$BIG_LAMA_DIR"

    local big_lama_zip="$LOG_DIR/big-lama.zip"
    local big_lama_expanded="$LOG_DIR/big-lama-expanded"
    export BIG_LAMA_ZIP="$big_lama_zip"
    export BIG_LAMA_EXPANDED="$big_lama_expanded"

    rm -rf "$big_lama_expanded"
    mkdir -p "$big_lama_expanded"

    log "Downloading Big-LaMa zip"
    curl -L --fail -o "$big_lama_zip" "https://huggingface.co/smartywu/big-lama/resolve/main/big-lama.zip" >>"$LOG_FILE" 2>&1 || fail "Big-LaMa zip download failed"

    log "Extracting Big-LaMa zip"
    if ! "$PY" - <<'PY' >>"$LOG_FILE" 2>&1
import os
import zipfile

with zipfile.ZipFile(os.environ["BIG_LAMA_ZIP"]) as archive:
    archive.extractall(os.environ["BIG_LAMA_EXPANDED"])
PY
    then
        fail "Big-LaMa unzip failed"
    fi

    if [[ -f "$big_lama_expanded/big-lama/config.yaml" ]]; then
        cp -a "$big_lama_expanded/big-lama/." "$BIG_LAMA_DIR/" >>"$LOG_FILE" 2>&1 || fail "Big-LaMa copy failed"
    else
        cp -a "$big_lama_expanded/." "$BIG_LAMA_DIR/" >>"$LOG_FILE" 2>&1 || fail "Big-LaMa copy failed"
    fi

    [[ -f "$BIG_LAMA_CKPT" ]] || fail "Big-LaMa checkpoint missing after unzip: $BIG_LAMA_CKPT"
}

copy_lama_for_pipeline() {
    log "Ensuring pipeline third_party LaMa checkpoint path exists"

    mkdir -p "$PIPELINE_LAMA_DIR/models"

    if [[ -f "$BIG_LAMA_DIR/config.yaml" ]]; then
        cp -f "$BIG_LAMA_DIR/config.yaml" "$PIPELINE_LAMA_DIR/config.yaml" >>"$LOG_FILE" 2>&1 || fail "Failed copying pipeline LaMa config"
    fi

    if [[ -f "$BIG_LAMA_DIR/models/best.ckpt" ]]; then
        cp -f "$BIG_LAMA_DIR/models/best.ckpt" "$PIPELINE_LAMA_DIR/models/best.ckpt" >>"$LOG_FILE" 2>&1 || fail "Failed copying pipeline LaMa checkpoint"
    fi

    [[ -f "$PIPELINE_LAMA_DIR/config.yaml" ]] || fail "Pipeline LaMa config missing"
    [[ -f "$PIPELINE_LAMA_DIR/models/best.ckpt" ]] || fail "Pipeline LaMa best.ckpt missing"
}

write_env_files() {
    log "Writing API/UI .env files"

    cat >"$API_DIR/.env" <<EOF
NODE_ENV=development
PORT=$API_PORT
MONGODB_URL=mongodb://localhost:27017/kone
JWT_SECRET=local_guest_secret
LOGIC_URL=http://localhost:$BACKEND_PORT
EOF

    cat >"$UI_DIR/.env" <<EOF
VITE_ENABLE_MOCK_API=false
VITE_API_BASE_URL=http://localhost:$API_PORT/api/v1
VITE_API_TIMEOUT=120000
EOF
}

run_checks() {
    log "Running setup checks"

    printf '\n============================================================\n'
    printf 'CHECKS\n'
    printf '============================================================\n'

    check_file "$PY"
    check_file "$PIPELINE_DIR/requirements.txt"
    check_file "$API_DIR/package.json"
    check_file "$UI_DIR/package.json"

    check_dir "$VENV_DIR"
    check_dir "$CACHE_DIR"
    check_dir "$HF_HOME"
    check_dir "$HUGGINGFACE_HUB_CACHE"
    check_dir "$PIP_CACHE_DIR"
    check_dir "$NPM_CONFIG_CACHE"
    check_dir "$TORCH_HOME"

    check_dir "$GDINO_DIR"
    check_dir "$SAM2_DIR"
    check_dir "$LAMA_DIR"
    check_dir "$BERT_DIR"
    check_dir "$BIG_LAMA_DIR"
    check_dir "$WEIGHTS_DIR"

    check_file "$BERT_DIR/config.json"
    check_file "$DINO_WEIGHT"
    check_file "$SAM2_WEIGHT"
    check_file "$BIG_LAMA_DIR/config.yaml"
    check_file "$BIG_LAMA_DIR/models/best.ckpt"
    check_file "$PIPELINE_LAMA_DIR/config.yaml"
    check_file "$PIPELINE_LAMA_DIR/models/best.ckpt"

    log "Checking Python version"
    "$PY" --version >>"$LOG_FILE" 2>&1 || fail "Python version check failed"

    log "Checking torch"
    "$PY" -c "import torch; print('torch:', torch.__version__, 'cuda:', torch.cuda.is_available())" >"$LOG_DIR/torch_check.txt" 2>>"$LOG_FILE" || fail "Torch import check failed"
    cat "$LOG_DIR/torch_check.txt"
    cat "$LOG_DIR/torch_check.txt" >>"$LOG_FILE"

    log "Checking core backend imports"
    "$PY" -c "import cv2, PIL, numpy, yaml, fastapi, uvicorn, psutil, imageio_ffmpeg; print(True)" >"$LOG_DIR/core_import_check.txt" 2>>"$LOG_FILE" || fail "Core backend import check failed"
    cat "$LOG_DIR/core_import_check.txt"
    cat "$LOG_DIR/core_import_check.txt" >>"$LOG_FILE"
    grep -Fq "True" "$LOG_DIR/core_import_check.txt" || fail "Core backend import check failed"

    log "Checking BERT local model and get_head_mask"
    if ! "$PY" - <<'PY' >"$LOG_DIR/bert_check.txt" 2>>"$LOG_FILE"
import os
from transformers import BertModel

os.environ["HF_HOME"] = os.environ["HF_HOME"]
os.environ["HUGGINGFACE_HUB_CACHE"] = os.environ["HUGGINGFACE_HUB_CACHE"]
os.environ["TRANSFORMERS_CACHE"] = os.environ["TRANSFORMERS_CACHE"]
model = BertModel.from_pretrained(os.environ["BERT_DIR"])
print(hasattr(model, "get_head_mask"))
PY
    then
        fail "BERT get_head_mask check failed"
    fi
    cat "$LOG_DIR/bert_check.txt"
    cat "$LOG_DIR/bert_check.txt" >>"$LOG_FILE"
    grep -Fq "True" "$LOG_DIR/bert_check.txt" || fail "BERT get_head_mask check failed"

    log "Checking GroundingDINO import"
    "$PY" -c "import groundingdino; print(True)" >"$LOG_DIR/groundingdino_import_check.txt" 2>>"$LOG_FILE" || fail "GroundingDINO import check failed"
    cat "$LOG_DIR/groundingdino_import_check.txt"
    cat "$LOG_DIR/groundingdino_import_check.txt" >>"$LOG_FILE"
    grep -Fq "True" "$LOG_DIR/groundingdino_import_check.txt" || fail "GroundingDINO import check failed"

    log "Checking SAM2 import"
    "$PY" -c "import sam2; print(True)" >"$LOG_DIR/sam2_import_check.txt" 2>>"$LOG_FILE" || fail "SAM2 import check failed"
    cat "$LOG_DIR/sam2_import_check.txt"
    cat "$LOG_DIR/sam2_import_check.txt" >>"$LOG_FILE"
    grep -Fq "True" "$LOG_DIR/sam2_import_check.txt" || fail "SAM2 import check failed"

    log "Checking LaMa source path"
    [[ -f "$LAMA_DIR/saicinpainting/__init__.py" ]] || fail "LaMa saicinpainting package missing"

    log "API npm packages installed"
    log "UI npm packages installed"

    printf '\nTRUE\nAll required checks passed.\nLogs: %s\n\n' "$LOG_FILE"
    log "All checks passed"
}

start_backend() {
    log "Starting backend"
    cd "$PIPELINE_DIR" || fail "Cannot cd into pipeline dir"
    activate_venv
    configure_backend_env
    "$PY" -m uvicorn server:app --app-dir "$PIPELINE_DIR/src" --host 0.0.0.0 --port "$BACKEND_PORT" --reload
}

start_api() {
    log "Starting API"
    cd "$API_DIR" || fail "Cannot cd into API dir"
    export NODE_ENV="development"
    export PORT="$API_PORT"
    export MONGODB_URL="mongodb://localhost:27017/kone"
    export JWT_SECRET="local_guest_secret"
    export LOGIC_URL="http://localhost:$BACKEND_PORT"
    export NPM_CONFIG_CACHE
    npm run dev
}

start_ui() {
    log "Starting UI"
    cd "$UI_DIR" || fail "Cannot cd into UI dir"
    export VITE_ENABLE_MOCK_API="false"
    export VITE_API_BASE_URL="http://localhost:$API_PORT/api/v1"
    export VITE_API_TIMEOUT="120000"
    export NPM_CONFIG_CACHE
    npm run dev
}

script_path() {
    if command -v realpath >/dev/null 2>&1; then
        realpath "$0"
    else
        readlink -f "$0"
    fi
}

launch_session() {
    local title="$1"
    local subcommand="$2"
    local script
    script="$(script_path)"

    if command -v gnome-terminal >/dev/null 2>&1; then
        gnome-terminal --title="$title" -- bash -lc "$(printf '%q %q %q' bash "$script" "$subcommand"); exec bash"
    elif command -v konsole >/dev/null 2>&1; then
        konsole --new-tab -p tabtitle="$title" -e bash -lc "$(printf '%q %q %q' bash "$script" "$subcommand"); exec bash"
    elif command -v xterm >/dev/null 2>&1; then
        xterm -T "$title" -e bash -lc "$(printf '%q %q %q' bash "$script" "$subcommand"); exec bash" &
    elif command -v tmux >/dev/null 2>&1; then
        local session_name
        session_name="$(printf '%s' "$title" | tr -cs 'A-Za-z0-9_' '_' | sed 's/_$//')"
        tmux new-session -d -s "$session_name" bash "$script" "$subcommand" || fail "tmux failed to launch $title"
        log "Started tmux session: $session_name"
    else
        log "No terminal emulator found; starting $title in background"
        nohup bash "$script" "$subcommand" >"$LOG_DIR/${subcommand}.log" 2>&1 &
        log "$title PID: $!"
    fi
}

start_all() {
    log "Opening backend/API/UI in separate Linux sessions"
    launch_session "KONE BACKEND $BACKEND_PORT" backend
    launch_session "KONE API $API_PORT" api
    launch_session "KONE UI $UI_PORT" ui
}

pipeline_check() {
    log "Running backend pipeline check"
    cd "$PIPELINE_DIR" || fail "Cannot cd into pipeline dir"
    activate_venv
    configure_backend_env
    "$PY" -m src.pipeline --config config.yaml
}

show_log() {
    printf '\nLog file:\n%s\n\n' "$LOG_FILE"
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$LOG_FILE" >/dev/null 2>&1 || true
    else
        less "$LOG_FILE"
    fi
}

menu() {
    while true; do
        cat <<EOF

============================================================
KONE SETUP / LAUNCHER
============================================================

[1] Start BACKEND only
[2] Start API only
[3] Start UI only
[4] Open BACKEND + API + UI in separate Linux sessions
[5] Run backend pipeline check
[6] Run local dependency checks again
[L] Open setup log
[X] Exit
EOF
        printf '\nChoose: '
        read -r choice

        case "$choice" in
            1) start_backend ;;
            2) start_api ;;
            3) start_ui ;;
            4) start_all ;;
            5) pipeline_check ;;
            6) run_checks ;;
            [Ll]) show_log ;;
            [Xx]) log "User selected exit"; exit 0 ;;
            *) printf 'Invalid choice: %s\n' "$choice" ;;
        esac
    done
}

main_setup() {
    create_dirs

    log "============================================================"
    log "KONE FULL SETUP STARTED"
    log "ROOT_DIR=$ROOT_DIR"
    log "LOG_FILE=$LOG_FILE"
    log "============================================================"

    cd "$ROOT_DIR" || fail "Cannot cd into ROOT_DIR"

    local python_base
    python_base="$(find_python)"
    log "Found required command: $python_base"

    require_cmd git
    require_cmd curl
    require_cmd node
    require_cmd npm
    require_cmd ffmpeg
    check_optional mongod

    create_venv
    upgrade_pip
    clone_repos
    install_python_requirements
    install_ai_repos
    download_models
    copy_lama_for_pipeline
    write_env_files
    run_checks
}

case "${1:-}" in
    backend)
        create_dirs
        start_backend
        ;;
    api)
        create_dirs
        start_api
        ;;
    ui)
        create_dirs
        start_ui
        ;;
    all)
        create_dirs
        start_all
        ;;
    pipeline-check)
        create_dirs
        pipeline_check
        ;;
    checks|check)
        create_dirs
        run_checks
        ;;
    setup)
        main_setup
        ;;
    "")
        main_setup
        menu
        ;;
    *)
        printf 'Usage: %s [setup|backend|api|ui|all|pipeline-check|checks]\n' "$0" >&2
        exit 2
        ;;
esac