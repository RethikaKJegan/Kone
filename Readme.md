# KONE AI Sales Visualisation Platform

KONE is a web application for creating AI-assisted elevator visualisations and
client-ready sales materials. Users can upload an image, select elevator
components, place them into the scene, generate previews or videos, and export
the final result.

## Tech stack

- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Radix UI, Zustand
- **API:** Node.js, Express, MongoDB, Mongoose, JWT authentication
- **AI backend:** Python, FastAPI, PyTorch
- **Computer vision:** GroundingDINO, SAM2, Depth Anything V2, OpenCV
- **Image generation and editing:** LaMa, FireRed Image Edit
- **Video generation:** ComfyUI and Wan 2.2 (optional)

## Requirements

For the complete AI workflow, use a Linux machine with:

- Python 3.11–3.13
- Node.js 20+ and npm
- MongoDB
- FFmpeg
- NVIDIA GPU with a compatible CUDA/PyTorch installation
- Git and curl

The frontend can run without a GPU when using the mock API. AI processing and
video generation require the configured models and GPU services.

## Installation

Run the setup script from the project root. It creates the Python environments,
installs dependencies, downloads the required model files, writes local .env
files, and runs setup checks.

~~~bash
cd /path/to/Kone
bash Kone_Setup_Python3.12_3.13.sh setup
~~~

The setup script may require a Hugging Face token when downloading restricted
model files:

~~~bash
export HF_TOKEN="your_huggingface_token"
bash Kone_Setup_Python3.12_3.13.sh setup
~~~

Keep tokens and service credentials outside the repository. Do not commit real
secrets to .env files or source control.

## Environment variables

The setup script creates these files:

- Frontend/kone-api-master/.env — API configuration
- Frontend/kone-ui-master/.env — frontend configuration

### API environment

~~~env
NODE_ENV=development
PORT=4000
MONGODB_URL=mongodb://localhost:27017/kone
JWT_SECRET=replace-with-a-long-random-secret
LOGIC_URL=http://localhost:8001
~~~

Optional integrations:

~~~env
AZURE_UPLOAD_ENABLED=false
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_CONTAINER_NAME=kone
BROCHURE_INTEGRATION_URL=https://api.sales-nxt.app/api/integrations/brochures
BROCHURE_INTEGRATION_API_KEY=
SMTP_HOST=
SMTP_PORT=
SMTP_USERNAME=
SMTP_PASSWORD=
EMAIL_FROM=
~~~

For AI video generation, the API can also use COMFY_AUTOSTART, COMFY_ROOT,
COMFY_URL, COMFY_RUNNER, COMFY_START_SCRIPT, and COMFY_PYTHON. The included
startup scripts provide local defaults for these values.

### Frontend environment

~~~env
VITE_ENABLE_MOCK_API=false
VITE_API_BASE_URL=http://localhost:4000/api/v1
VITE_API_TIMEOUT=120000
~~~

Set VITE_ENABLE_MOCK_API=true if you only want to run the frontend demo
without MongoDB or the backend services.

## Run locally

### Full local stack

If the project is located at /root/Kone, the included launcher starts MongoDB,
the Python backend, FireRed, the Node API, and the frontend:

~~~bash
cd /root/Kone
bash start_kone.sh
~~~

Open the application at http://localhost:3000.

The main service ports are:

| Service | Port | Purpose |
|---|---:|---|
| Frontend | 3000 | Web application |
| Node API | 4000 | REST API |
| Python AI backend | 8001 | Image processing and video orchestration |
| FireRed service | 8010 | AI image editing |
| ComfyUI | 8188 | Optional Wan video generation |
| MongoDB | 27017 | Application database |

To stop services and free the ports:

~~~bash
bash kill_ports.sh
~~~

### Run services separately

Use separate terminals when developing individual services:

~~~bash
# Terminal 1: MongoDB
mkdir -p .mongo/db
mongod --dbpath .mongo/db --bind_ip 127.0.0.1 --port 27017

# Terminal 2: Python backend + FireRed
bash start_logic_with_firered.sh

# Terminal 3: Node API
cd Frontend/kone-api-master
npm ci
npm run dev

# Terminal 4: Frontend
cd Frontend/kone-ui-master
npm ci
npm run dev
~~~

The frontend development server runs at http://localhost:3000 and the API
uses http://localhost:4000.

## Build and deploy

### Frontend

Build the production frontend:

~~~bash
cd Frontend/kone-ui-master
npm ci
npm run build
~~~

The production files are written to Frontend/kone-ui-master/dist/. Deploy that
folder to a static web server or CDN. Set VITE_API_BASE_URL before the build so
the compiled frontend points to the production API.

Preview the production build locally:

~~~bash
npm run preview
~~~

### Node API

The API does not require a compile step. Install production dependencies and
start it with production environment variables:

~~~bash
cd Frontend/kone-api-master
npm ci --omit=dev
NODE_ENV=production PORT=4000 node src/index.js
~~~

For production, run the API under a process manager such as PM2 or systemd,
and use a managed MongoDB instance or a secured MongoDB server.

### Python AI backend

The setup script creates the main Python environment in .venv. Start the
backend with:

~~~bash
cd elevator_mod_pipeline
../.venv/bin/python -m uvicorn server:app \
  --app-dir src \
  --host 0.0.0.0 \
  --port 8001
~~~

For production, keep the AI backend, FireRed, and ComfyUI on private network
ports and allow the Node API to access them through LOGIC_URL and the COMFY_*
settings.

## Useful commands

~~~bash
# Frontend checks
cd Frontend/kone-ui-master
npm run type-check
npm run lint
npm run test

# API checks
cd ../kone-api-master
npm test
npm run lint

# Backend setup checks
cd ../../
bash Kone_Setup_Python3.12_3.13.sh checks
~~~

API documentation is available at:

~~~text
http://localhost:4000/api/v1/docs
~~~

## Project folders

~~~text
Frontend/kone-ui-master/       React frontend
Frontend/kone-api-master/      Node.js/Express API
elevator_mod_pipeline/        Python AI backend and pipeline
models/                        Local AI model files
weights/                       Detection and segmentation weights
vdotest/                       ComfyUI and video workflows
start_kone.sh                  Full local launcher
Kone_Setup_Python3.12_3.13.sh  Dependency and model setup
~~~

## Troubleshooting

- If the API cannot connect, confirm MongoDB is running on port 27017.
- If AI processing fails, check GPU/CUDA availability and the setup log in
  setup_logs/.
- If the frontend calls the wrong API, check VITE_API_BASE_URL and restart the
  Vite server after changing it.
- If a port is already in use, run bash kill_ports.sh and start the stack again.
