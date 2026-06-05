@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem EDIT THESE TWO VALUES
rem ============================================================
set "ROOT_DIR=C:\Users\admin\Desktop\Kone-main\Kone-main"
set "HF_TOKEN=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"

rem ============================================================
rem PORTS
rem ============================================================
set "BACKEND_PORT=8001"
set "API_PORT=4000"
set "UI_PORT=3000"

rem ============================================================
rem CORE PATHS
rem ============================================================
set "VENV_DIR=%ROOT_DIR%\.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"
set "PIP=%VENV_DIR%\Scripts\pip.exe"

set "LOG_DIR=%ROOT_DIR%\setup_logs"
set "LOG_FILE=%LOG_DIR%\setup_kone_all.log"

set "CACHE_DIR=%ROOT_DIR%\.cache"
set "HF_HOME=%ROOT_DIR%\.hf_home"
set "HUGGINGFACE_HUB_CACHE=%ROOT_DIR%\.hf_home\hub"
set "TRANSFORMERS_CACHE=%ROOT_DIR%\.hf_home\hub"
set "HF_HUB_CACHE=%ROOT_DIR%\.hf_home\hub"
set "TORCH_HOME=%ROOT_DIR%\.cache\torch"
set "XDG_CACHE_HOME=%ROOT_DIR%\.cache"
set "PIP_CACHE_DIR=%ROOT_DIR%\.cache\pip"
set "NPM_CONFIG_CACHE=%ROOT_DIR%\.cache\npm"
set "MPLCONFIGDIR=%ROOT_DIR%\.cache\matplotlib"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
set "HF_HUB_ENABLE_HF_TRANSFER=0"

set "PIPELINE_DIR=%ROOT_DIR%\elevator_mod_pipeline"
set "API_DIR=%ROOT_DIR%\Frontend\kone-api-master"
set "UI_DIR=%ROOT_DIR%\Frontend\kone-ui-master"

set "GDINO_DIR=%ROOT_DIR%\GroundingDINO"
set "SAM2_DIR=%ROOT_DIR%\sam2_src"
set "LAMA_DIR=%ROOT_DIR%\lama"
set "BERT_DIR=%ROOT_DIR%\bert-base-uncased"
set "WEIGHTS_DIR=%ROOT_DIR%\weights"
set "BIG_LAMA_DIR=%ROOT_DIR%\big-lama"
set "PIPELINE_LAMA_DIR=%PIPELINE_DIR%\third_party\lama\big-lama"

set "DINO_WEIGHT=%WEIGHTS_DIR%\groundingdino_swint_ogc.pth"
set "SAM2_WEIGHT=%WEIGHTS_DIR%\sam2.1_hiera_large.pt"
set "BIG_LAMA_CKPT=%BIG_LAMA_DIR%\models\best.ckpt"

rem ============================================================
rem CREATE ROOT-LOCAL LOG/CACHE DIRS
rem ============================================================
if not exist "%ROOT_DIR%" (
    echo ERROR: ROOT_DIR does not exist: %ROOT_DIR%
    pause
    exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%CACHE_DIR%" mkdir "%CACHE_DIR%"
if not exist "%HF_HOME%" mkdir "%HF_HOME%"
if not exist "%HUGGINGFACE_HUB_CACHE%" mkdir "%HUGGINGFACE_HUB_CACHE%"
if not exist "%TORCH_HOME%" mkdir "%TORCH_HOME%"
if not exist "%PIP_CACHE_DIR%" mkdir "%PIP_CACHE_DIR%"
if not exist "%NPM_CONFIG_CACHE%" mkdir "%NPM_CONFIG_CACHE%"
if not exist "%MPLCONFIGDIR%" mkdir "%MPLCONFIGDIR%"
if not exist "%WEIGHTS_DIR%" mkdir "%WEIGHTS_DIR%"

call :log "============================================================"
call :log "KONE FULL SETUP STARTED"
call :log "ROOT_DIR=%ROOT_DIR%"
call :log "LOG_FILE=%LOG_FILE%"
call :log "============================================================"

cd /d "%ROOT_DIR%" || call :fail "Cannot cd into ROOT_DIR"

call :require_cmd python
call :require_cmd git
call :require_cmd curl
call :require_cmd node
call :require_cmd npm

call :require_cmd ffmpeg
call :check_optional mongod

call :create_venv
call :upgrade_pip
call :clone_repos
call :install_python_requirements
call :install_ai_repos
call :download_models
call :copy_lama_for_pipeline
call :write_env_files
call :run_checks

goto menu


rem ============================================================
rem MENU
rem ============================================================
:menu
echo.
echo ============================================================
echo KONE SETUP / LAUNCHER
echo ============================================================
echo.
echo [1] Start BACKEND only
echo [2] Start API only
echo [3] Start UI only
echo [4] Open BACKEND + API + UI in separate CMD windows
echo [5] Run backend pipeline check
echo [6] Run local dependency checks again
echo [L] Open setup log
echo [X] Exit
echo.
choice /C 123456LX /N /M "Choose: "

if errorlevel 8 goto exit_ok
if errorlevel 7 goto show_log
if errorlevel 6 goto checks_again
if errorlevel 5 goto pipeline_check
if errorlevel 4 goto start_all
if errorlevel 3 goto start_ui
if errorlevel 2 goto start_api
if errorlevel 1 goto start_backend

goto menu


rem ============================================================
rem RUN TARGETS
rem ============================================================
:start_backend
call :log "Starting backend in current CMD window"
cd /d "%PIPELINE_DIR%" || call :fail "Cannot cd into pipeline dir"
call "%VENV_DIR%\Scripts\activate.bat"

set "PYTHONPATH=%PIPELINE_DIR%\src;%ROOT_DIR%;%GDINO_DIR%;%SAM2_DIR%;%LAMA_DIR%"
set "HF_HOME=%ROOT_DIR%\.hf_home"
set "HUGGINGFACE_HUB_CACHE=%ROOT_DIR%\.hf_home\hub"
set "TRANSFORMERS_CACHE=%ROOT_DIR%\.hf_home\hub"
set "HF_HUB_CACHE=%ROOT_DIR%\.hf_home\hub"
set "TORCH_HOME=%ROOT_DIR%\.cache\torch"
set "XDG_CACHE_HOME=%ROOT_DIR%\.cache"
set "MPLCONFIGDIR=%ROOT_DIR%\.cache\matplotlib"

uvicorn server:app --app-dir "%PIPELINE_DIR%\src" --host 0.0.0.0 --port %BACKEND_PORT% --reload
goto menu


:start_api
call :log "Starting API in current CMD window"
cd /d "%API_DIR%" || call :fail "Cannot cd into API dir"

set "NODE_ENV=development"
set "PORT=%API_PORT%"
set "MONGODB_URL=mongodb://localhost:27017/kone"
set "JWT_SECRET=local_guest_secret"
set "LOGIC_URL=http://localhost:%BACKEND_PORT%"
set "NPM_CONFIG_CACHE=%ROOT_DIR%\.cache\npm"

npm run dev
goto menu


:start_ui
call :log "Starting UI in current CMD window"
cd /d "%UI_DIR%" || call :fail "Cannot cd into UI dir"

set "VITE_ENABLE_MOCK_API=false"
set "VITE_API_BASE_URL=http://localhost:%API_PORT%/api/v1"
set "VITE_API_TIMEOUT=120000"
set "NPM_CONFIG_CACHE=%ROOT_DIR%\.cache\npm"

npm run dev
goto menu


:start_all
call :log "Opening backend/API/UI in separate CMD windows"

start "KONE BACKEND 8001" cmd /k "cd /d "%PIPELINE_DIR%" && call "%VENV_DIR%\Scripts\activate.bat" && set PYTHONPATH=%PIPELINE_DIR%\src;%ROOT_DIR%;%GDINO_DIR%;%SAM2_DIR%;%LAMA_DIR% && set HF_HOME=%ROOT_DIR%\.hf_home && set HUGGINGFACE_HUB_CACHE=%ROOT_DIR%\.hf_home\hub && set TRANSFORMERS_CACHE=%ROOT_DIR%\.hf_home\hub && set HF_HUB_CACHE=%ROOT_DIR%\.hf_home\hub && set TORCH_HOME=%ROOT_DIR%\.cache\torch && set XDG_CACHE_HOME=%ROOT_DIR%\.cache && set MPLCONFIGDIR=%ROOT_DIR%\.cache\matplotlib && uvicorn server:app --app-dir "%PIPELINE_DIR%\src" --host 0.0.0.0 --port %BACKEND_PORT% --reload"

start "KONE API 4000" cmd /k "cd /d "%API_DIR%" && set NODE_ENV=development && set PORT=%API_PORT% && set MONGODB_URL=mongodb://localhost:27017/kone && set JWT_SECRET=local_guest_secret && set LOGIC_URL=http://localhost:%BACKEND_PORT% && set NPM_CONFIG_CACHE=%ROOT_DIR%\.cache\npm && npm run dev"

start "KONE UI 3000" cmd /k "cd /d "%UI_DIR%" && set VITE_ENABLE_MOCK_API=false && set VITE_API_BASE_URL=http://localhost:%API_PORT%/api/v1 && set VITE_API_TIMEOUT=120000 && set NPM_CONFIG_CACHE=%ROOT_DIR%\.cache\npm && npm run dev"

goto menu


:pipeline_check
call :log "Running backend pipeline check"
cd /d "%PIPELINE_DIR%" || call :fail "Cannot cd into pipeline dir"
call "%VENV_DIR%\Scripts\activate.bat"

set "PYTHONPATH=%PIPELINE_DIR%\src;%ROOT_DIR%;%GDINO_DIR%;%SAM2_DIR%;%LAMA_DIR%"
set "HF_HOME=%ROOT_DIR%\.hf_home"
set "HUGGINGFACE_HUB_CACHE=%ROOT_DIR%\.hf_home\hub"
set "TRANSFORMERS_CACHE=%ROOT_DIR%\.hf_home\hub"
set "HF_HUB_CACHE=%ROOT_DIR%\.hf_home\hub"
set "TORCH_HOME=%ROOT_DIR%\.cache\torch"
set "XDG_CACHE_HOME=%ROOT_DIR%\.cache"
set "MPLCONFIGDIR=%ROOT_DIR%\.cache\matplotlib"
set "TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu"

"%PY%" -m src.pipeline --config config.yaml
goto menu


:checks_again
call :run_checks
goto menu


:show_log
echo.
echo Log file:
echo %LOG_FILE%
echo.
notepad "%LOG_FILE%"
goto menu


:exit_ok
call :log "User selected exit"
exit /b 0


rem ============================================================
rem SETUP STEPS
rem ============================================================
:create_venv
if exist "%PY%" (
    call :log "Python venv already exists: %VENV_DIR%"
    "%PY%" --version >>"%LOG_FILE%" 2>&1
    exit /b 0
)

call :log "Creating Python venv: %VENV_DIR%"
python -m venv "%VENV_DIR%" >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "Failed to create Python venv"

"%PY%" --version >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "Venv Python check failed"

exit /b 0


:upgrade_pip
call :log "Upgrading pip/setuptools/wheel"
"%PY%" -m ensurepip --upgrade >>"%LOG_FILE%" 2>&1
"%PY%" -m pip install --cache-dir "%PIP_CACHE_DIR%" --upgrade pip setuptools wheel >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "pip upgrade failed"
exit /b 0


:clone_repos
call :log "Cloning/updating AI repos"

if not exist "%GDINO_DIR%\.git" (
    if exist "%GDINO_DIR%" (
        call :log "GroundingDINO dir exists without .git; keeping existing dir"
    ) else (
        git clone https://github.com/IDEA-Research/GroundingDINO.git "%GDINO_DIR%" >>"%LOG_FILE%" 2>&1
        if errorlevel 1 call :fail "GroundingDINO clone failed"
    )
) else (
    cd /d "%GDINO_DIR%" && git pull >>"%LOG_FILE%" 2>&1
)

if not exist "%SAM2_DIR%\.git" (
    if exist "%SAM2_DIR%" (
        call :log "sam2_src dir exists without .git; keeping existing dir"
    ) else (
        git clone https://github.com/facebookresearch/sam2.git "%SAM2_DIR%" >>"%LOG_FILE%" 2>&1
        if errorlevel 1 call :fail "SAM2 clone failed"
    )
) else (
    cd /d "%SAM2_DIR%" && git pull >>"%LOG_FILE%" 2>&1
)

if not exist "%LAMA_DIR%\.git" (
    if exist "%LAMA_DIR%" (
        call :log "lama dir exists without .git; keeping existing dir"
    ) else (
        git clone https://github.com/advimman/lama.git "%LAMA_DIR%" >>"%LOG_FILE%" 2>&1
        if errorlevel 1 call :fail "LaMa clone failed"
    )
) else (
    cd /d "%LAMA_DIR%" && git pull >>"%LOG_FILE%" 2>&1
)

cd /d "%ROOT_DIR%" || call :fail "Cannot return to ROOT_DIR"
exit /b 0


:install_python_requirements
call :log "Installing Python 3.13-compatible Torch stack"

"%PIP%" install --cache-dir "%PIP_CACHE_DIR%" --index-url "%TORCH_INDEX_URL%" "torch>=2.7" "torchvision>=0.22" "torchaudio>=2.7" >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "Failed installing Torch stack"

call :log "Installing project-side backend requirements"

if exist "%PIPELINE_DIR%\requirements.txt" (
    "%PIP%" install --cache-dir "%PIP_CACHE_DIR%" -r "%PIPELINE_DIR%\requirements.txt" >>"%LOG_FILE%" 2>&1
    if errorlevel 1 call :fail "Failed installing elevator_mod_pipeline requirements.txt"
) else (
    call :fail "Missing project requirements: %PIPELINE_DIR%\requirements.txt"
)

call :log "Installing backend extras"
"%PIP%" install --cache-dir "%PIP_CACHE_DIR%" psutil imageio-ffmpeg opencv-python pillow numpy scipy pyyaml requests tqdm uvicorn fastapi python-multipart >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "Failed installing backend extras"

call :log "Ensuring Python 3.13-compatible Hugging Face stack"
"%PIP%" install --cache-dir "%PIP_CACHE_DIR%" --upgrade "transformers>=4.45,<5" "tokenizers>=0.20" "huggingface_hub[cli]>=0.25" >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "Failed installing transformers/tokenizers/huggingface_hub"
call :log "Installing API npm packages"
if exist "%API_DIR%\package.json" (
    cd /d "%API_DIR%" || call :fail "Cannot cd into API dir"
    npm install --cache "%NPM_CONFIG_CACHE%" >>"%LOG_FILE%" 2>&1
    if errorlevel 1 call :fail "API npm install failed"
) else (
    call :fail "Missing API package.json"
)

call :log "Installing UI npm packages"
if exist "%UI_DIR%\package.json" (
    cd /d "%UI_DIR%" || call :fail "Cannot cd into UI dir"
    npm install --cache "%NPM_CONFIG_CACHE%" >>"%LOG_FILE%" 2>&1
    if errorlevel 1 call :fail "UI npm install failed"
) else (
    call :fail "Missing UI package.json"
)

cd /d "%ROOT_DIR%" || call :fail "Cannot return to ROOT_DIR"
exit /b 0


:install_ai_repos
call :log "Installing third-party AI repo requirements"

call :log "Skipping GroundingDINO requirements.txt to avoid Python 3.13 dependency downgrades"

call :log "Installing LaMa-compatible deps for Python 3.13"

"%PIP%" install --cache-dir "%PIP_CACHE_DIR%" "numpy>=1.26,<2" scipy joblib threadpoolctl cython wheel setuptools "scikit-image>=0.24,<0.26" "scikit-learn>=1.5" "pytorch-lightning>=2.5,<3" "kornia>=0.7.4,<0.9" "albumentations>=2.0,<3" omegaconf==2.3.0 hydra-core==1.3.2 antlr4-python3-runtime==4.9.3 einops webdataset easydict >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "Failed installing Python 3.13 LaMa deps"

call :log "Ensuring torch is installed before GroundingDINO editable build"
"%PY%" -m pip install --cache-dir "%PIP_CACHE_DIR%" --index-url "%TORCH_INDEX_URL%" "torch>=2.7" "torchvision>=0.22" "torchaudio>=2.7" >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "Torch install before GroundingDINO failed"

call :log "Editable installing GroundingDINO"
"%PY%" -m pip install --cache-dir "%PIP_CACHE_DIR%" --no-build-isolation -e "%GDINO_DIR%" >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "GroundingDINO editable install failed"
"%PIP%" install --cache-dir "%PIP_CACHE_DIR%" --upgrade "transformers>=4.45,<5" "tokenizers>=0.20" "huggingface_hub[cli]>=0.25" >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "Failed restoring Python 3.13-compatible Hugging Face stack after GroundingDINO"
call :log "Editable installing SAM2"
"%PIP%" install --cache-dir "%PIP_CACHE_DIR%" -e "%SAM2_DIR%" >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "SAM2 editable install failed"

exit /b 0


:download_models
call :log "Preparing model/cache downloads under ROOT_DIR"

if /I not "%HF_TOKEN%"=="PUT_YOUR_HF_TOKEN_HERE" (
    set "HUGGING_FACE_HUB_TOKEN=%HF_TOKEN%"
    call :log "HF_TOKEN provided"
) else (
    call :log "HF_TOKEN not set; public downloads will be attempted without login"
)

call :download_bert
call :download_groundingdino_weight
call :download_sam2_weight
call :download_big_lama

exit /b 0


:download_bert
call :log "Checking bert-base-uncased"

if exist "%BERT_DIR%\config.json" (
    call :log "BERT already exists: %BERT_DIR%"
    exit /b 0
)

call :log "Downloading bert-base-uncased into %BERT_DIR%"
"%PY%" -c "import os; os.environ['HF_HOME']=r'%HF_HOME%'; os.environ['HUGGINGFACE_HUB_CACHE']=r'%HUGGINGFACE_HUB_CACHE%'; os.environ['TRANSFORMERS_CACHE']=r'%TRANSFORMERS_CACHE%'; from huggingface_hub import snapshot_download; token=r'%HF_TOKEN%'; token=None if token=='PUT_YOUR_HF_TOKEN_HERE' else token; snapshot_download(repo_id='google-bert/bert-base-uncased', local_dir=r'%BERT_DIR%', local_dir_use_symlinks=False, token=token)" >>"%LOG_FILE%"
if errorlevel 1 call :fail "bert-base-uncased download failed"

exit /b 0


:download_groundingdino_weight
call :log "Checking GroundingDINO SwinT weight"

if exist "%DINO_WEIGHT%" (
    call :log "GroundingDINO weight already exists: %DINO_WEIGHT%"
    exit /b 0
)

call :log "Downloading GroundingDINO weight into %DINO_WEIGHT%"
curl -L --fail -o "%DINO_WEIGHT%" "https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth" >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "GroundingDINO weight download failed"

exit /b 0


:download_sam2_weight
call :log "Checking SAM2.1 Hiera Large weight"

if exist "%SAM2_WEIGHT%" (
    call :log "SAM2 weight already exists: %SAM2_WEIGHT%"
    exit /b 0
)

call :log "Downloading SAM2.1 Hiera Large weight into %WEIGHTS_DIR%"
"%PY%" -c "import os; os.environ['HF_HOME']=r'%HF_HOME%'; os.environ['HUGGINGFACE_HUB_CACHE']=r'%HUGGINGFACE_HUB_CACHE%'; os.environ['TRANSFORMERS_CACHE']=r'%TRANSFORMERS_CACHE%'; from huggingface_hub import hf_hub_download; token=r'%HF_TOKEN%'; token=None if token=='PUT_YOUR_HF_TOKEN_HERE' else token; hf_hub_download(repo_id='facebook/sam2.1-hiera-large', filename='sam2.1_hiera_large.pt', local_dir=r'%WEIGHTS_DIR%', token=token)" >>"%LOG_FILE%"

if errorlevel 1 (
    call :log "HF SAM2 download failed; trying SAM2 checkpoint script with bash"
    where bash >nul 2>&1
    if errorlevel 1 call :fail "SAM2 weight download failed and bash is unavailable"

    cd /d "%SAM2_DIR%\checkpoints" || call :fail "Cannot cd into SAM2 checkpoints dir"
    bash download_ckpts.sh >>"%LOG_FILE%" 2>&1
    if errorlevel 1 call :fail "SAM2 download_ckpts.sh failed"

    if exist "%SAM2_DIR%\checkpoints\sam2.1_hiera_large.pt" (
        copy /Y "%SAM2_DIR%\checkpoints\sam2.1_hiera_large.pt" "%SAM2_WEIGHT%" >>"%LOG_FILE%" 2>&1
    )
)

if not exist "%SAM2_WEIGHT%" call :fail "SAM2 weight missing after download"

cd /d "%ROOT_DIR%" || call :fail "Cannot return to ROOT_DIR"
exit /b 0


:download_big_lama
call :log "Checking Big-LaMa checkpoint"

if exist "%BIG_LAMA_CKPT%" (
    call :log "Big-LaMa checkpoint already exists: %BIG_LAMA_CKPT%"
    exit /b 0
)

if not exist "%BIG_LAMA_DIR%" mkdir "%BIG_LAMA_DIR%"

set "BIG_LAMA_ZIP=%LOG_DIR%\big-lama.zip"
set "BIG_LAMA_EXPANDED=%LOG_DIR%\big-lama-expanded"

if exist "%BIG_LAMA_EXPANDED%" rmdir /S /Q "%BIG_LAMA_EXPANDED%"

call :log "Downloading Big-LaMa zip"
curl -L --fail -o "%BIG_LAMA_ZIP%" "https://huggingface.co/smartywu/big-lama/resolve/main/big-lama.zip" >>"%LOG_FILE%"
if errorlevel 1 call :fail "Big-LaMa zip download failed"

call :log "Extracting Big-LaMa zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%BIG_LAMA_ZIP%' -DestinationPath '%BIG_LAMA_EXPANDED%' -Force" >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "Big-LaMa unzip failed"

if exist "%BIG_LAMA_EXPANDED%\big-lama\config.yaml" (
    xcopy /E /I /Y "%BIG_LAMA_EXPANDED%\big-lama" "%BIG_LAMA_DIR%" >>"%LOG_FILE%" 2>&1
) else (
    xcopy /E /I /Y "%BIG_LAMA_EXPANDED%" "%BIG_LAMA_DIR%" >>"%LOG_FILE%" 2>&1
)

if not exist "%BIG_LAMA_CKPT%" call :fail "Big-LaMa checkpoint missing after unzip: %BIG_LAMA_CKPT%"

exit /b 0


:copy_lama_for_pipeline
call :log "Ensuring pipeline third_party LaMa checkpoint path exists"

if not exist "%PIPELINE_LAMA_DIR%" mkdir "%PIPELINE_LAMA_DIR%"
if not exist "%PIPELINE_LAMA_DIR%\models" mkdir "%PIPELINE_LAMA_DIR%\models"

if exist "%BIG_LAMA_DIR%\config.yaml" (
    copy /Y "%BIG_LAMA_DIR%\config.yaml" "%PIPELINE_LAMA_DIR%\config.yaml" >>"%LOG_FILE%" 2>&1
)

if exist "%BIG_LAMA_DIR%\models\best.ckpt" (
    copy /Y "%BIG_LAMA_DIR%\models\best.ckpt" "%PIPELINE_LAMA_DIR%\models\best.ckpt" >>"%LOG_FILE%" 2>&1
)

if not exist "%PIPELINE_LAMA_DIR%\config.yaml" call :fail "Pipeline LaMa config missing"
if not exist "%PIPELINE_LAMA_DIR%\models\best.ckpt" call :fail "Pipeline LaMa best.ckpt missing"

exit /b 0


:write_env_files
call :log "Writing API/UI .env files"

(
echo NODE_ENV=development
echo PORT=%API_PORT%
echo MONGODB_URL=mongodb://localhost:27017/kone
echo JWT_SECRET=local_guest_secret
echo LOGIC_URL=http://localhost:%BACKEND_PORT%
) > "%API_DIR%\.env"

(
echo VITE_ENABLE_MOCK_API=false
echo VITE_API_BASE_URL=http://localhost:%API_PORT%/api/v1
echo VITE_API_TIMEOUT=120000
) > "%UI_DIR%\.env"

exit /b 0


:run_checks
call :log "Running setup checks"

echo.
echo ============================================================
echo CHECKS
echo ============================================================

call :check_file "%PY%"
call :check_file "%PIPELINE_DIR%\requirements.txt"
call :check_file "%API_DIR%\package.json"
call :check_file "%UI_DIR%\package.json"

call :check_dir "%VENV_DIR%"
call :check_dir "%CACHE_DIR%"
call :check_dir "%HF_HOME%"
call :check_dir "%HUGGINGFACE_HUB_CACHE%"
call :check_dir "%PIP_CACHE_DIR%"
call :check_dir "%NPM_CONFIG_CACHE%"
call :check_dir "%TORCH_HOME%"

call :check_dir "%GDINO_DIR%"
call :check_dir "%SAM2_DIR%"
call :check_dir "%LAMA_DIR%"
call :check_dir "%BERT_DIR%"
call :check_dir "%BIG_LAMA_DIR%"
call :check_dir "%WEIGHTS_DIR%"

call :check_file "%BERT_DIR%\config.json"
call :check_file "%DINO_WEIGHT%"
call :check_file "%SAM2_WEIGHT%"
call :check_file "%BIG_LAMA_DIR%\config.yaml"
call :check_file "%BIG_LAMA_DIR%\models\best.ckpt"
call :check_file "%PIPELINE_LAMA_DIR%\config.yaml"
call :check_file "%PIPELINE_LAMA_DIR%\models\best.ckpt"

call :log "Checking Python version"
"%PY%" --version >>"%LOG_FILE%" 2>&1
if errorlevel 1 call :fail "Python version check failed"

call :log "Checking torch"
"%PY%" -c "import torch; print('torch:', torch.__version__, 'cuda:', torch.cuda.is_available())" > "%LOG_DIR%\torch_check.txt" 2>>"%LOG_FILE%"
type "%LOG_DIR%\torch_check.txt"
type "%LOG_DIR%\torch_check.txt" >>"%LOG_FILE%"
if errorlevel 1 call :fail "Torch import check failed"

call :log "Checking core backend imports"
"%PY%" -c "import cv2, PIL, numpy, yaml, fastapi, uvicorn, psutil, imageio_ffmpeg; print(True)" > "%LOG_DIR%\core_import_check.txt" 2>>"%LOG_FILE%"
type "%LOG_DIR%\core_import_check.txt"
type "%LOG_DIR%\core_import_check.txt" >>"%LOG_FILE%"
findstr /C:"True" "%LOG_DIR%\core_import_check.txt" >nul
if errorlevel 1 call :fail "Core backend import check failed"

call :log "Checking BERT local model and get_head_mask"
"%PY%" -c "import os; os.environ['HF_HOME']=r'%HF_HOME%'; os.environ['HUGGINGFACE_HUB_CACHE']=r'%HUGGINGFACE_HUB_CACHE%'; os.environ['TRANSFORMERS_CACHE']=r'%TRANSFORMERS_CACHE%'; from transformers import BertModel; m=BertModel.from_pretrained(r'%BERT_DIR%'); print(hasattr(m,'get_head_mask'))" > "%LOG_DIR%\bert_check.txt" 2>>"%LOG_FILE%"
type "%LOG_DIR%\bert_check.txt"
type "%LOG_DIR%\bert_check.txt" >>"%LOG_FILE%"
findstr /C:"True" "%LOG_DIR%\bert_check.txt" >nul
if errorlevel 1 call :fail "BERT get_head_mask check failed"

call :log "Checking GroundingDINO import"
"%PY%" -c "import groundingdino; print(True)" > "%LOG_DIR%\groundingdino_import_check.txt" 2>>"%LOG_FILE%"
type "%LOG_DIR%\groundingdino_import_check.txt"
type "%LOG_DIR%\groundingdino_import_check.txt" >>"%LOG_FILE%"
findstr /C:"True" "%LOG_DIR%\groundingdino_import_check.txt" >nul
if errorlevel 1 call :fail "GroundingDINO import check failed"

call :log "Checking SAM2 import"
"%PY%" -c "import sam2; print(True)" > "%LOG_DIR%\sam2_import_check.txt" 2>>"%LOG_FILE%"
type "%LOG_DIR%\sam2_import_check.txt"
type "%LOG_DIR%\sam2_import_check.txt" >>"%LOG_FILE%"
findstr /C:"True" "%LOG_DIR%\sam2_import_check.txt" >nul
if errorlevel 1 call :fail "SAM2 import check failed"

call :log "Checking LaMa source path"
if not exist "%LAMA_DIR%\saicinpainting\__init__.py" call :fail "LaMa saicinpainting package missing"

call :log "API npm packages installed"
call :log "UI npm packages installed"

echo.
echo TRUE
echo All required checks passed.
echo Logs: %LOG_FILE%
echo.

call :log "All checks passed"
exit /b 0


rem ============================================================
rem HELPERS
rem ============================================================
:log
echo [%date% %time%] %~1
echo [%date% %time%] %~1>>"%LOG_FILE%"
exit /b 0


:fail
echo.
echo ERROR: %~1
echo ERROR: %~1>>"%LOG_FILE%"
echo.
echo Check log:
echo %LOG_FILE%
echo.
pause
exit /b 1


:require_cmd
where %~1 >nul 2>&1
if errorlevel 1 (
    call :fail "Missing required command: %~1"
)
call :log "Found required command: %~1"
exit /b 0


:check_optional
where %~1 >nul 2>&1
if errorlevel 1 (
    call :log "WARNING: Optional command not found: %~1"
) else (
    call :log "Found optional command: %~1"
)
exit /b 0


:check_file
if exist "%~1" (
    call :log "OK file: %~1"
) else (
    call :fail "Missing file: %~1"
)
exit /b 0


:check_dir
if exist "%~1\" (
    call :log "OK dir: %~1"
) else (
    call :fail "Missing dir: %~1"
)
exit /b 0