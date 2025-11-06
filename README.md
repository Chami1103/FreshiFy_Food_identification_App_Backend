# 🥗 FreshiFy — Food Identification Backend

A modular, AI-powered backend for monitoring food freshness using **image recognition**, **gas-sensor analysis**, and **real-time logging**. Designed for IoT integration, Dockerized/cloud deployment (AWS EC2), and horizontal scaling.

---

## 🌍 Project overview

This repository contains three Flask microservices that together form the FreshiFy backend. Each service focuses on a specific domain and shares common database utilities (MongoDB).

**Services**

| Service            |                                                            Purpose | Default port |
| ------------------ | -----------------------------------------------------------------: | :----------: |
| **Sensor Backend** |              Predicts food spoilage from NH₃ gas + RGB sensor data |    `5000`    |
| **Image Backend**  | Classifies fruit images (fresh vs spoiled) with a TensorFlow model |    `5001`    |
| **Notify Backend** |    Manages notifications, calendar events, blogs, and expense logs |    `5002`    |

---

## 🧭 Repository structure

```
FreshiFy_Mobile_App_Backend/
├── app/
│   ├── DB_FreshiFy.py                 # MongoDB connection & helpers
│   ├── main_App.py                    # Launcher for all microservices
│   ├── Notify_Alerts.py               # Notifications / Calendar / Blogs backend
│   ├── Image_Processing/
│   │   └── Image_Flask_API_Endpoints.py
│   ├── Sensor_module/
│   │   └── Sensor_Flask_API_Endpoints.py
│   └── models/
│       ├── Fruit_Classifier.h5
│       ├── logistic_regression_model.pkl
│       ├── label_encoder.joblib
│       └── scaler.joblib
├── scripts/
│   ├── setup_env.ps1
│   ├── deploy_ec2.sh
│   └── start_local.sh
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env
└── README.md
```

---

## ⚙️ Prerequisites

* **Python** ≥ 3.12
* **pip** (latest)
* **MongoDB** ≥ 6.0 (local or cloud)
* PowerShell or Bash
* Git (recommended)

---

## 🚀 Quick start (recommended)

Run the PowerShell helper from the repository root (Windows):

```powershell
.\scripts\setup_env.ps1
```

This script will:

* Create and activate a Python 3.12 virtual environment
* Install dependencies from `requirements.txt`
* Start all services

Manual setup (alternative):

```powershell
cd E:\FreshiFy_Mobile_App_Backend
py -3.12 -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python app\main_App.py
```

---

## 🌐 Service endpoints & health checks

| Service | Base URL                | Key endpoints                                       |
| ------- | ----------------------- | --------------------------------------------------- |
| Sensor  | `http://localhost:5000` | `/predict-sensor`, `/health`                        |
| Image   | `http://localhost:5001` | `/predict-image`, `/health`                         |
| Notify  | `http://localhost:5002` | `/notify`, `/calendar/add`, `/blogs/add`, `/health` |

---

## 🔑 Environment variables (`.env`)

Create a `.env` file in the project root and set values appropriate for your environment:

```env
# Ports
SENSOR_PORT=5000
IMAGE_PORT=5001
NOTIFY_PORT=5002

# Backend host for mobile (example)
EXPO_PUBLIC_BACKEND_HOST=192.168.8.102

# MongoDB
MONGODB_URI=mongodb://localhost:27017
DB_NAME=DB_FreshiFy

# Current user
CURRENT_USER=chamika

# Model paths
MODEL_PATH=./app/models/Fruit_Classifier.h5
SENSOR_MODEL_PATH=./app/models/logistic_regression_model.pkl
SENSOR_SCALER_PATH=./app/models/scaler.joblib
SENSOR_LABEL_ENCODER_PATH=./app/models/label_encoder.joblib

# Logging & CORS
LOG_LEVEL=INFO
CORS_ORIGINS=*
```

---

## 🧠 Machine learning models

* `Fruit_Classifier.h5` — TensorFlow CNN for fruit-type and freshness classification.
* `logistic_regression_model.pkl` — scikit-learn model for sensor-based freshness prediction.
* `scaler.joblib` — StandardScaler used for sensor inputs.
* `label_encoder.joblib` — Encodes/decodes class labels.

All models are loaded dynamically when each microservice starts. Ensure model files are present under `app/models/`.

---

## 📦 Major dependencies

Key libraries (pinned in `requirements.txt`):

* `Flask` — web framework
* `Flask-CORS` — CORS support
* `tensorflow` — image model
* `scikit-learn` — sensor ML
* `pandas`, `numpy` — data processing
* `pymongo` — MongoDB connector
* `waitress` — production WSGI server
* `python-dotenv` — environment loader

---

## 🧾 Data flow (summary)

**Sensor module**

* Accepts NH₃ and RGB readings from IoT devices
* Normalizes inputs (scaler) and predicts fresh/spoiled
* Logs results to MongoDB (`sensors_data` collection)

**Image module**

* Accepts image uploads at `/predict-image`
* Runs CNN to classify fruit type and freshness
* Stores metadata and results in MongoDB (`images_data`)

**Notify module**

* Manages user alerts, calendar events, blogs, and expense tracking
* Provides CRUD endpoints for front-end/mobile use

---

## 📊 Visualization ideas (future)

* Plotly Dash — interactive freshness dashboards
* Streamlit — quick reports and model inspection UI
* Grafana — real-time NH₃ trend monitoring (via time-series DB)

Example local visualizer (future):

```bash
python visualizer/dashboard.py
```

---

## ☁️ Docker & AWS EC2 deployment

Use `docker-compose` to run everything locally or on a VM:

```bash
docker-compose up --build -d
```

This brings up:

* MongoDB
* Sensor API
* Image API
* Notify API

To deploy to EC2, use the provided helper:

```bash
./scripts/deploy_ec2.sh
```

---

## 🧰 Troubleshooting

* **`Import "dotenv" could not be resolved`** — activate the virtual environment before running code.
* **TensorFlow missing** — run `pip install tensorflow==2.19.0` or ensure installation completed.
* **MongoDB connection failed** — start `mongod` or confirm `MONGODB_URI`.
* **Port in use (WinError 10048)** — stop prior services or change ports in `.env`.
* **Model path invalid** — verify model files exist at paths referenced in `.env`.

---

## 👨‍💻 Author

**Chamika Vimukthi** — Full Stack / ML Developer

* Role: Full Stack / ML Developer
* Tech stack: Flask · TensorFlow · MongoDB · AWS EC2 · Python 3.12

---

## 📜 License

MIT License © 2025 Chamika Vimukthi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell copies of the Software, subject to
the following conditions.

---

### ✅ What I included

* Clean, production-oriented `README.md` covering setup, services, env vars, models, troubleshooting, and deployment quick-start.

---

Would you like me to also create `visualizer/dashboard.py` (Streamlit or Plotly) and an example `docker-compose.override.yml` for development? If yes, pick **Streamlit** or **Plotly Dash** and I’ll scaffold it next.
