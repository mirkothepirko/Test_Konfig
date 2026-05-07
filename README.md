# Test_Konfig — FLEX TABLE Prototyp

Plattenkonfigurator-Prototyp: Browser-Frontend → FastAPI → APS Fusion Automation → STEP-Download.

## Voraussetzungen

1. Python 3.11+
2. APS-App mit 2-legged OAuth (Client-ID + Secret)
3. Fusion 360 mit User Parameters `Breite`, `Tiefe`, `R_Ecke`, `R_Kante`, `Dicke` im Referenzmodell

## Setup

```bash
cd backend
cp .env.example .env
# .env mit echten APS_CLIENT_ID / APS_CLIENT_SECRET befüllen

pip install -r requirements.txt
```

## Einmalig: APS registrieren

Fusion Add-In-Ordner (`backend/aps_addin/flex_table/`) muss `flex_reference.f3d` enthalten.

```bash
cd backend
python scripts/setup_aps.py
```

## Backend starten

```bash
cd backend
uvicorn main:app --reload --port 8000
```

## Frontend öffnen

```bash
cd frontend
python -m http.server 3000
# Browser: http://localhost:3000
```

## Tests

```bash
cd backend
pytest -v
```

## Parameter (FLEX TABLE)

| Parameter  | Min  | Max  | Default | Einheit |
|------------|------|------|---------|---------|
| breite     | 600  | 1800 | 1200    | mm      |
| tiefe      | 400  | 900  | 600     | mm      |
| r_ecke     | 0    | 50   | 0       | mm      |
| r_kante    | 0    | 5    | 0       | mm      |
| dicke      | —    | —    | 28.6    | mm      |
