#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-/root/Kone}"
HF_TOKEN="${HF_TOKEN:-PUT_YOUR_HF_TOKEN_HERE}"

BACKEND_PORT="${BACKEND_PORT:-8001}"
API_PORT="${API_PORT:-4000}"
UI_PORT="${UI_PORT:-3000}"

VENV_DIR="$ROOT_DIR/.venv"
PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu128}"
CPU_TORCH_INDEX_URL="${CPU_TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}"

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
VDOTEST_DIR="$ROOT_DIR/vdotest"
COMFY_DIR="$VDOTEST_DIR/ComfyUI"
COMFY_VENV_DIR="$COMFY_DIR/.venv"
COMFY_PY="$COMFY_VENV_DIR/bin/python"
COMFY_PIP="$COMFY_VENV_DIR/bin/pip"
COMFY_WORKFLOW_DIR="$VDOTEST_DIR/workflows"
COMFY_INPUT_DIR="$COMFY_DIR/input"
COMFY_OUTPUT_DIR="$COMFY_DIR/output"
COMFY_MODEL_PRECISION="${COMFY_MODEL_PRECISION:-fp8}"

GDINO_DIR="$ROOT_DIR/GroundingDINO"
SAM2_DIR="$ROOT_DIR/sam2_src"
LAMA_DIR="$ROOT_DIR/lama"
BERT_DIR="$ROOT_DIR/bert-base-uncased"
DEPTH_MODEL_DIR="$ROOT_DIR/models/depth-anything-v2-base-hf"
REFINEMENT_MODEL_DIR="$ROOT_DIR/models/stable-diffusion-inpainting"
FIRERED_VENV_DIR="$ROOT_DIR/firered_venv"
FIRERED_PY="$FIRERED_VENV_DIR/bin/python"
FIRERED_PIP="$FIRERED_VENV_DIR/bin/pip"
FIRERED_MODEL_REPO="${FIRERED_MODEL_REPO:-FireRedTeam/FireRed-Image-Edit-1.1}"
FIRERED_MODEL_DIR="$ROOT_DIR/models/FireRed-Image-Edit-1.1"
FIRERED_HF_HOME="$ROOT_DIR/firered_hf_cache"
FIRERED_HF_HUB_CACHE="$FIRERED_HF_HOME/hub"
WEIGHTS_DIR="$ROOT_DIR/weights"
BIG_LAMA_DIR="$ROOT_DIR/big-lama"
PIPELINE_LAMA_DIR="$PIPELINE_DIR/third_party/lama/big-lama"

DINO_WEIGHT="$WEIGHTS_DIR/groundingdino_swint_ogc.pth"
SAM2_WEIGHT="$WEIGHTS_DIR/sam2.1_hiera_large.pt"
BIG_LAMA_CKPT="$BIG_LAMA_DIR/models/best.ckpt"

export ROOT_DIR HF_TOKEN BACKEND_PORT API_PORT UI_PORT VENV_DIR PY PIP TORCH_INDEX_URL CPU_TORCH_INDEX_URL
export LOG_DIR LOG_FILE CACHE_DIR HF_HOME HUGGINGFACE_HUB_CACHE TRANSFORMERS_CACHE HF_HUB_CACHE
export TORCH_HOME XDG_CACHE_HOME PIP_CACHE_DIR NPM_CONFIG_CACHE MPLCONFIGDIR
export HF_HUB_DISABLE_SYMLINKS_WARNING HF_HUB_ENABLE_HF_TRANSFER
export PIPELINE_DIR API_DIR UI_DIR VDOTEST_DIR COMFY_DIR COMFY_VENV_DIR COMFY_PY COMFY_PIP
export COMFY_WORKFLOW_DIR COMFY_INPUT_DIR COMFY_OUTPUT_DIR COMFY_MODEL_PRECISION
export GDINO_DIR SAM2_DIR LAMA_DIR BERT_DIR DEPTH_MODEL_DIR REFINEMENT_MODEL_DIR
export FIRERED_VENV_DIR FIRERED_PY FIRERED_PIP FIRERED_MODEL_REPO FIRERED_MODEL_DIR
export FIRERED_HF_HOME FIRERED_HF_HUB_CACHE WEIGHTS_DIR
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

find_preferred_python() {
    local env_name="$1"
    shift

    local override=""
    case "$env_name" in
        firered) override="${PY_FIRERED_BASE:-}" ;;
        comfy) override="${PY_COMFY_BASE:-}" ;;
    esac

    if [[ -n "$override" ]]; then
        command -v "$override" >/dev/null 2>&1 || fail "$env_name Python command not found: $override"
        printf "%s\n" "$override"
        return 0
    fi

    local candidate
    for candidate in "$@"; do
        if command -v "$candidate" >/dev/null 2>&1; then
            printf "%s\n" "$candidate"
            return 0
        fi
    done

    fail "Missing Python for $env_name; tried: $*"
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
        printf "ERROR: ROOT_DIR does not exist: %s\n" "$ROOT_DIR" >&2
        exit 1
    }

    mkdir -p "$LOG_DIR" "$CACHE_DIR" "$HF_HOME" "$HUGGINGFACE_HUB_CACHE"
    mkdir -p "$TORCH_HOME" "$PIP_CACHE_DIR" "$NPM_CONFIG_CACHE" "$MPLCONFIGDIR" "$WEIGHTS_DIR"
    mkdir -p "$ROOT_DIR/models" "$FIRERED_HF_HOME" "$FIRERED_HF_HUB_CACHE"
    mkdir -p "$VDOTEST_DIR" "$COMFY_WORKFLOW_DIR" "$COMFY_INPUT_DIR" "$COMFY_OUTPUT_DIR"
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
    clone_or_pull "ComfyUI" "https://github.com/comfyanonymous/ComfyUI.git" "$COMFY_DIR"
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

create_named_venv() {
    local env_name="$1"
    local venv_dir="$2"
    shift 2

    local py_bin="$venv_dir/bin/python"
    if [[ -x "$py_bin" ]]; then
        log "$env_name venv already exists: $venv_dir"
        "$py_bin" --version >>"$LOG_FILE" 2>&1 || fail "$env_name venv Python check failed"
        return 0
    fi

    local python_base
    python_base="$(find_preferred_python "$env_name" "$@")"
    log "Creating $env_name Python venv with $python_base: $venv_dir"
    "$python_base" -m venv "$venv_dir" >>"$LOG_FILE" 2>&1 || fail "Failed creating $env_name venv"
    "$py_bin" -m ensurepip --upgrade >>"$LOG_FILE" 2>&1 || fail "$env_name ensurepip failed"
    "$py_bin" -m pip install --cache-dir "$PIP_CACHE_DIR" --upgrade pip setuptools wheel >>"$LOG_FILE" 2>&1 || fail "$env_name pip upgrade failed"
}

create_firered_venv() {
    create_named_venv "firered" "$FIRERED_VENV_DIR" python3.11 python3.12 python3.13 python3 python
}

create_comfy_venv() {
    create_named_venv "comfy" "$COMFY_VENV_DIR" python3.12 python3.11 python3.13 python3 python
}

install_firered_requirements() {
    log "Installing FireRed CUDA inference requirements"
    create_firered_venv
    "$FIRERED_PIP" install --cache-dir "$PIP_CACHE_DIR" --index-url "$TORCH_INDEX_URL" "torch>=2.7" "torchvision>=0.22" "torchaudio>=2.7" >>"$LOG_FILE" 2>&1 || fail "FireRed Torch install failed"
    "$FIRERED_PIP" install --cache-dir "$PIP_CACHE_DIR" --upgrade "diffusers>=0.35" "transformers>=4.56,<5" "accelerate>=1.10" "sentencepiece>=0.2" "protobuf>=5" "safetensors>=0.4.5" pillow requests fastapi uvicorn python-multipart >>"$LOG_FILE" 2>&1 || fail "FireRed dependency install failed"
}

install_comfyui() {
    log "Installing/updating ComfyUI for Wan 2.2 workflows"
    clone_or_pull "ComfyUI" "https://github.com/comfyanonymous/ComfyUI.git" "$COMFY_DIR"
    mkdir -p "$COMFY_INPUT_DIR" "$COMFY_OUTPUT_DIR" "$COMFY_DIR/models/diffusion_models" "$COMFY_DIR/models/loras" "$COMFY_DIR/models/text_encoders" "$COMFY_DIR/models/vae"
    create_comfy_venv
    "$COMFY_PIP" install --cache-dir "$PIP_CACHE_DIR" --index-url "$TORCH_INDEX_URL" "torch>=2.7" "torchvision>=0.22" "torchaudio>=2.7" >>"$LOG_FILE" 2>&1 || fail "ComfyUI Torch install failed"
    if [[ -f "$COMFY_DIR/requirements.txt" ]]; then
        "$COMFY_PIP" install --cache-dir "$PIP_CACHE_DIR" -r "$COMFY_DIR/requirements.txt" >>"$LOG_FILE" 2>&1 || fail "ComfyUI requirements install failed"
    else
        fail "Missing ComfyUI requirements.txt: $COMFY_DIR/requirements.txt"
    fi
    "$COMFY_PIP" install --cache-dir "$PIP_CACHE_DIR" --upgrade huggingface_hub[cli] imageio-ffmpeg opencv-python >>"$LOG_FILE" 2>&1 || fail "ComfyUI extra dependency install failed"
}

hf_token_arg() {
    if [[ -n "${HF_TOKEN:-}" && "${HF_TOKEN,,}" != "put_your_hf_token_here" ]]; then
        printf "%s" "$HF_TOKEN"
    fi
}

snapshot_model() {
    local repo_id="$1"
    local local_dir="$2"
    local marker_file="$3"

    if [[ -f "$marker_file" ]]; then
        log "Model already exists: $local_dir"
        return 0
    fi

    mkdir -p "$local_dir"
    log "Downloading Hugging Face snapshot $repo_id -> $local_dir"
    HF_DOWNLOAD_REPO_ID="$repo_id" HF_DOWNLOAD_LOCAL_DIR="$local_dir" "$PY" - <<PY >>"$LOG_FILE" 2>&1
import os
from huggingface_hub import snapshot_download

token = os.environ.get("HF_TOKEN")
if not token or token.lower() == "put_your_hf_token_here":
    token = None

snapshot_download(
    repo_id=os.environ["HF_DOWNLOAD_REPO_ID"],
    local_dir=os.environ["HF_DOWNLOAD_LOCAL_DIR"],
    local_dir_use_symlinks=False,
    token=token,
)
PY
}

download_hf_file() {
    local repo_id="$1"
    local filename="$2"
    local local_dir="$3"
    local final_path="$local_dir/$(basename "$filename")"

    if [[ -f "$final_path" ]]; then
        log "Model file already exists: $final_path"
        return 0
    fi

    mkdir -p "$local_dir"
    log "Downloading Hugging Face file $repo_id/$filename -> $local_dir"
    HF_DOWNLOAD_REPO_ID="$repo_id" HF_DOWNLOAD_FILENAME="$filename" HF_DOWNLOAD_LOCAL_DIR="$local_dir" "$PY" - <<PY >>"$LOG_FILE" 2>&1
import os
from huggingface_hub import hf_hub_download

token = os.environ.get("HF_TOKEN")
if not token or token.lower() == "put_your_hf_token_here":
    token = None

hf_hub_download(
    repo_id=os.environ["HF_DOWNLOAD_REPO_ID"],
    filename=os.environ["HF_DOWNLOAD_FILENAME"],
    local_dir=os.environ["HF_DOWNLOAD_LOCAL_DIR"],
    token=token,
)
PY
}

download_firered_model() {
    log "Checking FireRed Image Edit model"
    if [[ -f "$FIRERED_MODEL_DIR/model_index.json" ]]; then
        log "FireRed model already exists: $FIRERED_MODEL_DIR"
        return 0
    fi
    HF_HOME="$FIRERED_HF_HOME" HF_HUB_CACHE="$FIRERED_HF_HUB_CACHE" HUGGINGFACE_HUB_CACHE="$FIRERED_HF_HUB_CACHE" snapshot_model "$FIRERED_MODEL_REPO" "$FIRERED_MODEL_DIR" "$FIRERED_MODEL_DIR/model_index.json" || fail "FireRed model download failed"
}

download_depth_and_refinement_models() {
    snapshot_model "depth-anything/Depth-Anything-V2-Base-hf" "$DEPTH_MODEL_DIR" "$DEPTH_MODEL_DIR/config.json" || fail "Depth Anything model download failed"
    snapshot_model "runwayml/stable-diffusion-inpainting" "$REFINEMENT_MODEL_DIR" "$REFINEMENT_MODEL_DIR/model_index.json" || fail "Stable Diffusion inpainting model download failed"
}

download_comfy_wan_models() {
    log "Checking ComfyUI Wan 2.2 I2V models"
    local diffusion_suffix="fp8_scaled"
    if [[ "$COMFY_MODEL_PRECISION" == "fp16" ]]; then
        diffusion_suffix="fp16"
    fi

    download_hf_file "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" "split_files/diffusion_models/wan2.2_i2v_high_noise_14B_${diffusion_suffix}.safetensors" "$COMFY_DIR/models/diffusion_models" || fail "Wan high-noise model download failed"
    download_hf_file "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" "split_files/diffusion_models/wan2.2_i2v_low_noise_14B_${diffusion_suffix}.safetensors" "$COMFY_DIR/models/diffusion_models" || fail "Wan low-noise model download failed"
    download_hf_file "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" "$COMFY_DIR/models/loras" || fail "Wan high-noise LoRA download failed"
    download_hf_file "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" "$COMFY_DIR/models/loras" || fail "Wan low-noise LoRA download failed"
    download_hf_file "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" "split_files/vae/wan_2.1_vae.safetensors" "$COMFY_DIR/models/vae" || fail "Wan VAE download failed"
    download_hf_file "Comfy-Org/Wan_2.1_ComfyUI_repackaged" "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" "$COMFY_DIR/models/text_encoders" || fail "Wan text encoder download failed"
}

patch_pipeline_config_paths() {
    log "Updating pipeline config paths for this ROOT_DIR"
    "$PY" - <<PY >>"$LOG_FILE" 2>&1
import os
from pathlib import Path
import yaml

root = Path(os.environ["ROOT_DIR"])
config_path = root / "elevator_mod_pipeline" / "config.yaml"
with config_path.open("r", encoding="utf-8") as handle:
    cfg = yaml.safe_load(handle)

video = cfg.setdefault("video", {})
geometry = cfg.setdefault("geometry", {})
refinement = cfg.setdefault("refinement", {})
comfy = video.setdefault("comfy", {})

precision = os.environ.get("COMFY_MODEL_PRECISION", "fp8")
suffix = "fp16" if precision == "fp16" else "fp8_scaled"
comfy.update({
    "root_dir": str(root / "vdotest" / "ComfyUI"),
    "workflow_dir": str(root / "vdotest" / "workflows"),
    "input_dir": str(root / "vdotest" / "ComfyUI" / "input"),
    "output_dir": str(root / "vdotest" / "ComfyUI" / "output"),
    "high_noise_model": f"wan2.2_i2v_high_noise_14B_{suffix}.safetensors",
    "low_noise_model": f"wan2.2_i2v_low_noise_14B_{suffix}.safetensors",
    "high_noise_lora": "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
    "low_noise_lora": "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors",
    "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "vae_name": "wan_2.1_vae.safetensors",
})
geometry["depth_model_id"] = str(root / "models" / "depth-anything-v2-base-hf")
refinement["model_id"] = str(root / "models" / "stable-diffusion-inpainting")

with config_path.open("w", encoding="utf-8") as handle:
    yaml.safe_dump(cfg, handle, sort_keys=False)
PY
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
    download_depth_and_refinement_models
    download_firered_model
    download_comfy_wan_models
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

    printf "\n============================================================\n"
    printf "CHECKS\n"
    printf "============================================================\n"

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
    check_dir "$FIRERED_VENV_DIR"
    check_dir "$COMFY_DIR"
    check_dir "$COMFY_VENV_DIR"
    check_dir "$COMFY_DIR/models/diffusion_models"
    check_dir "$COMFY_DIR/models/loras"
    check_dir "$COMFY_DIR/models/text_encoders"
    check_dir "$COMFY_DIR/models/vae"

    check_file "$BERT_DIR/config.json"
    check_file "$DINO_WEIGHT"
    check_file "$SAM2_WEIGHT"
    check_file "$BIG_LAMA_DIR/config.yaml"
    check_file "$BIG_LAMA_DIR/models/best.ckpt"
    check_file "$PIPELINE_LAMA_DIR/config.yaml"
    check_file "$PIPELINE_LAMA_DIR/models/best.ckpt"
    check_file "$FIRERED_PY"
    check_file "$COMFY_PY"
    check_file "$FIRERED_MODEL_DIR/model_index.json"
    check_file "$DEPTH_MODEL_DIR/config.json"
    check_file "$REFINEMENT_MODEL_DIR/model_index.json"
    if [[ "$COMFY_MODEL_PRECISION" == "fp16" ]]; then
        check_file "$COMFY_DIR/models/diffusion_models/wan2.2_i2v_high_noise_14B_fp16.safetensors"
        check_file "$COMFY_DIR/models/diffusion_models/wan2.2_i2v_low_noise_14B_fp16.safetensors"
    else
        check_file "$COMFY_DIR/models/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
        check_file "$COMFY_DIR/models/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
    fi
    check_file "$COMFY_DIR/models/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"
    check_file "$COMFY_DIR/models/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"
    check_file "$COMFY_DIR/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    check_file "$COMFY_DIR/models/vae/wan_2.1_vae.safetensors"

    log "Checking Python version"
    "$PY" --version >>"$LOG_FILE" 2>&1 || fail "Python version check failed"

    log "Checking torch"
    "$PY" -c 'import torch; print("torch:", torch.__version__, "cuda:", torch.cuda.is_available())' >"$LOG_DIR/torch_check.txt" 2>>"$LOG_FILE" || fail "Torch import check failed"
    cat "$LOG_DIR/torch_check.txt"
    cat "$LOG_DIR/torch_check.txt" >>"$LOG_FILE"

    log "Checking core backend imports"
    "$PY" -c "import cv2, PIL, numpy, yaml, fastapi, uvicorn, psutil, imageio_ffmpeg; print(True)" >"$LOG_DIR/core_import_check.txt" 2>>"$LOG_FILE" || fail "Core backend import check failed"
    cat "$LOG_DIR/core_import_check.txt"
    cat "$LOG_DIR/core_import_check.txt" >>"$LOG_FILE"
    grep -Fq "True" "$LOG_DIR/core_import_check.txt" || fail "Core backend import check failed"

    log "Checking BERT local model and get_head_mask"
    if ! "$PY" - <<PY >"$LOG_DIR/bert_check.txt" 2>>"$LOG_FILE"
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

    log "Checking FireRed imports"
    "$FIRERED_PY" -c "import torch, diffusers, transformers, accelerate, fastapi, uvicorn; print(True)" >"$LOG_DIR/firered_import_check.txt" 2>>"$LOG_FILE" || fail "FireRed import check failed"
    cat "$LOG_DIR/firered_import_check.txt"
    cat "$LOG_DIR/firered_import_check.txt" >>"$LOG_FILE"
    grep -Fq "True" "$LOG_DIR/firered_import_check.txt" || fail "FireRed import check failed"

    log "Checking ComfyUI imports"
    "$COMFY_PY" -c "import torch, aiohttp, yaml, PIL, safetensors; print(True)" >"$LOG_DIR/comfy_import_check.txt" 2>>"$LOG_FILE" || fail "ComfyUI import check failed"
    cat "$LOG_DIR/comfy_import_check.txt"
    cat "$LOG_DIR/comfy_import_check.txt" >>"$LOG_FILE"
    grep -Fq "True" "$LOG_DIR/comfy_import_check.txt" || fail "ComfyUI import check failed"

    log "Checking LaMa source path"
    [[ -f "$LAMA_DIR/saicinpainting/__init__.py" ]] || fail "LaMa saicinpainting package missing"

    log "API npm packages installed"
    log "UI npm packages installed"

    printf "\nTRUE\nAll required checks passed.\nLogs: %s\n\n" "$LOG_FILE"
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

start_comfy() {
    log "Starting ComfyUI"
    cd "$COMFY_DIR" || fail "Cannot cd into ComfyUI dir"
    export HF_HOME="$HF_HOME"
    export HF_HUB_CACHE="$HF_HUB_CACHE"
    export HUGGINGFACE_HUB_CACHE="$HUGGINGFACE_HUB_CACHE"
    export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
    "$COMFY_PY" main.py --listen 0.0.0.0 --port 8188
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
    launch_session "KONE COMFYUI 8188" comfy
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
[4] Open BACKEND + API + UI + ComfyUI in separate Linux sessions
[5] Start ComfyUI only
[6] Run backend pipeline check
[7] Run local dependency checks again
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
            5) start_comfy ;;
            6) pipeline_check ;;
            7) run_checks ;;
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
    install_firered_requirements
    install_comfyui
    download_models
    copy_lama_for_pipeline
    patch_pipeline_config_paths
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
    comfy)
        create_dirs
        start_comfy
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
        printf 'Usage: %s [setup|backend|api|ui|comfy|all|pipeline-check|checks]\n' "$0" >&2
        exit 2
        ;;
esac