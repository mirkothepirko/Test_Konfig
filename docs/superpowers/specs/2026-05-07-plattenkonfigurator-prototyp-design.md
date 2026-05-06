# Design: Test_Konfig — Plattenkonfigurator Prototyp

**Datum:** 2026-05-07  
**Status:** Genehmigt  
**Ziel:** Sauberer Neustart des Plattenkonfigurators. APS/Fusion-Pfad von A bis Z durchspielen — ohne den Pivot-Ballast des alten Repos.

---

## Kontext

Das bestehende Repo `Plattenkonfigurator` hat durch den CadQuery → APS-Pivot (2026-05-04 → 2026-05-05) unaufgeräumten Zustand. `Test_Konfig` ist ein sauberer Schnitt: gleicher APS-Stack, aber minimale Architektur ohne alten Code.

Sobald der APS-Pfad stabil läuft, wird das Frontend auf React Three Fiber aufgebaut.

---

## Scope

- **Plattenfamilie:** FLEX TABLE (einzige Familie im Prototyp)
- **Backend:** APS Design Automation für Fusion (2-legged OAuth)
- **Frontend:** Vanilla HTML/CSS/JS + Three.js via CDN (kein Build-Step)
- **Output:** STEP-Download + Live-3D-Vorschau im Browser

---

## Repo-Struktur

```
Test_Konfig/
├── frontend/
│   └── index.html              # Gesamtes Frontend in einer Datei
├── backend/
│   ├── main.py                 # FastAPI App (3 Endpoints)
│   ├── aps_client.py           # 2-legged Auth + WorkItem Submit/Poll/Download
│   ├── aps_addin/
│   │   └── flex_table/
│   │       ├── flex_addin.py   # Fusion Add-In: params lesen → Parameter setzen → STEP exportieren
│   │       └── flex_reference.f3d  # Fusion-Referenzmodell (Git LFS)
│   ├── .env.example            # APS_CLIENT_ID, APS_CLIENT_SECRET
│   └── requirements.txt
├── .gitattributes              # LFS für *.f3d, *.f3z
└── README.md
```

---

## Parameter (FLEX TABLE)

| Parameter | Min | Max | Default | Einheit | Notiz |
|---|---|---|---|---|---|
| `breite` | 600 | 1800 | 1200 | mm | Slider + Zahleneingabe |
| `tiefe` | 400 | 900 | 600 | mm | Slider + Zahleneingabe |
| `r_ecke` | 0 | 50 | 0 | mm | Eckenradius |
| `r_kante` | 0 | 5 | 0 | mm | Kantenradius |
| `dicke` | — | — | 28.6 | mm | Konstante, kein UI-Element |

---

## Datenfluss

```
Browser                    FastAPI                    APS
  │                           │                         │
  │  POST /configure          │                         │
  │  {breite, tiefe,          │                         │
  │   r_ecke, r_kante}        │                         │
  │──────────────────────────>│                         │
  │                           │  Token holen (2-legged) │
  │                           │<────────────────────────>│
  │                           │  WorkItem submittenn    │
  │                           │  (params.json + f3d)    │
  │                           │────────────────────────>│
  │  {workItemId}             │                         │
  │<──────────────────────────│                         │
  │                           │                         │
  │  GET /status/{id}  (Poll) │                         │
  │──────────────────────────>│  WorkItem Status abfragen│
  │  {status, progress}       │<────────────────────────>│
  │<──────────────────────────│                         │
  │                           │                         │
  │  GET /download/{id}       │                         │
  │──────────────────────────>│  STEP-Datei aus OSS     │
  │  (binary .step)           │<────────────────────────│
  │<──────────────────────────│                         │
```

---

## API-Endpoints (FastAPI)

### `POST /configure`
**Body:**
```json
{
  "breite": 1200,
  "tiefe": 600,
  "r_ecke": 0,
  "r_kante": 0
}
```
**Response:**
```json
{ "workItemId": "abc123..." }
```

### `GET /status/{workItemId}`
**Response:**
```json
{
  "status": "inProgress",
  "progress": 45
}
```
`status` ∈ `pending | inProgress | succeeded | failed`

### `GET /download/{workItemId}`
**Response:** Binary STEP-Datei als `attachment`

---

## Frontend (index.html)

Zwei-Spalten-Layout, kein Build:

```
┌──────────────────────┬──────────────────────────────────┐
│  PARAMETER           │  3D-VORSCHAU                     │
│                      │                                  │
│  Breite [====●] 1200 │  ┌──────────────────────────┐   │
│  Tiefe  [==●  ]  600 │  │   Three.js Canvas        │   │
│  R_Ecke [●    ]    0 │  │   Box skaliert live      │   │
│  R_Kante[●    ]    0 │  └──────────────────────────┘   │
│                      │                                  │
│  [Für CNC exportieren]  Status: Bereit                  │
│  [STEP herunterladen]   [████████░░] 80%                │
└──────────────────────┴──────────────────────────────────┘
```

**Verhalten:**
- Slider und Zahleneingabe sind gekoppelt
- Three.js Box skaliert live bei jedem Slider-Move (proportionale Größenvorschau, kein echter Radius)
- "Für CNC exportieren" → POST `/configure`, Polling startet (alle 2s GET `/status`)
- Bei `succeeded`: Download-Button aktiv → GET `/download`
- Bei `failed`: Fehlermeldung anzeigen

---

## Fusion Add-In (`flex_addin.py`)

```
Ablauf (headless, APS-Worker):
1. params.json lesen
2. flex_reference.f3d öffnen
3. User Parameters setzen: Breite, Tiefe, R_Ecke, R_Kante, Dicke=28.6
4. result.step exportieren
```

**APS Activity (einmalig registrieren):**
- Engine: `Autodesk.Fusion+2701_00`
- Input: `params.json` (inline JSON), `flex_reference.f3d` (aus OSS Bucket)
- Output: `result.step` (in OSS Bucket)

---

## APS-Konfiguration (`aps_client.py`)

- 2-legged Token wird beim ersten Call geholt
- Automatische Erneuerung wenn Restlaufzeit < 5 min
- Client-ID/Secret ausschließlich aus `.env`
- Bestehende APS-App: `plattenkonfigurator-backend` (Hub Flötotto, Abo `77799003002466`)

---

## Voraussetzungen (manuell in Fusion, einmalig)

Bevor der APS-Pfad getestet werden kann, muss der User in Fusion 360:
1. User Parameters anlegen: `Breite`, `Tiefe`, `R_Ecke`, `R_Kante`, `Dicke`
2. Alle Extrusions/Sketches auf diese Parameter referenzieren
3. Modell auf Defaults zurückstellen (1200×600, R_Ecke=0, R_Kante=0, Dicke=28.6)
4. Als `backend/aps_addin/flex_table/flex_reference.f3d` speichern und per Git LFS committen

---

## Erfolgs-Kriterien

- [ ] `POST /configure` startet ein APS WorkItem ohne Fehler
- [ ] `GET /status` liefert korrekten Fortschritt
- [ ] `GET /download` liefert eine valide STEP-Datei
- [ ] STEP öffnet sich in Fusion 360 oder einem CNC-Programm ohne Fehler
- [ ] Dimensionen der STEP-Datei stimmen mit den eingegebenen Parametern überein
- [ ] Frontend läuft ohne Build-Step im Browser

---

## Bewusste Einschränkungen (Prototyp)

- Kein Auth (kein Login, kein User-Management)
- Kein Caching identischer Konfigurationen
- Keine Fehlerbehandlung für ungültige Parameterkombinationen
- Three.js-Vorschau zeigt nur Box-Größe, keine Radien
- Nur FLEX TABLE — FRAME TABLE und A-TABLE kommen später
