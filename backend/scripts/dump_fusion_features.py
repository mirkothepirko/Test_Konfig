"""
Fusion 360 Skript: dumpt alle relevanten Features aus dem aktiven Design
in eine features.json, damit das Three.js-Frontend sie nachbauen kann.

Verwendung:
  1. Fusion 360 öffnen
  2. Datei -> Öffnen -> backend/aps_addin/flex_table/flex_reference.f3d
  3. Werkzeuge -> Skripts und Add-Ins -> Skripte -> "+ Skript erstellen oder importieren"
     -> "Aus vorhandenem Skript importieren" -> dieses File auswählen
  4. Skript markieren -> Ausführen

Schreibt nach:
  backend/aps_addin/flex_table/features.json

Was dumpt wird:
  - Alle User-Parameter mit Expression + aktuellem Wert
  - Alle Timeline-Features (Name, Typ, Suppression-State)
  - Hole-Features: Position relativ zu allen 4 Plattenecken + Mitte + Bohrungsdaten
  - Sketches: alle Sketch-Punkte (für Körnungen / Markierungspunkte)
  - Body-Bounding-Box als Referenzrahmen

Damit kann das Frontend pro Feature entscheiden, an welcher Ecke/Kante
es verankert ist (kleinster Abstand) und auf veränderte Breite/Tiefe
parametrisch reagieren — ohne dass wir das Modell-Setup raten müssen.
"""
import adsk.core
import adsk.fusion
import json
import os
import traceback


def _mm(value_cm):
    """Fusion internal units are cm. Convert to mm."""
    return round(value_cm * 10.0, 4)


def _point_dict(p):
    return {"x": _mm(p.x), "y": _mm(p.y), "z": _mm(p.z)}


def _bbox_corners(bbox):
    mn, mx = bbox.minPoint, bbox.maxPoint
    return {
        "min": _point_dict(mn),
        "max": _point_dict(mx),
        "center": {
            "x": _mm((mn.x + mx.x) / 2),
            "y": _mm((mn.y + mx.y) / 2),
            "z": _mm((mn.z + mx.z) / 2),
        },
        "size": {
            "x": _mm(mx.x - mn.x),
            "y": _mm(mx.y - mn.y),
            "z": _mm(mx.z - mn.z),
        },
    }


def _offsets_from_plate(point, bbox):
    """For a world-space point, offsets from each face of the plate bbox.
    Frontend uses these to pick the anchoring rule (smallest offset wins)."""
    mn, mx = bbox.minPoint, bbox.maxPoint
    return {
        "from_min_x": _mm(point.x - mn.x),
        "from_max_x": _mm(mx.x - point.x),
        "from_min_y": _mm(point.y - mn.y),
        "from_max_y": _mm(mx.y - point.y),
        "from_min_z": _mm(point.z - mn.z),
        "from_max_z": _mm(mx.z - point.z),
    }


def _user_params(design):
    out = []
    for p in design.userParameters:
        out.append({
            "name": p.name,
            "expression": p.expression,
            "value_mm": _mm(p.value),
            "unit": p.unit,
            "comment": p.comment or "",
        })
    return out


def _pos_record(world_point, plate_bbox):
    return {
        "world": _point_dict(world_point),
        "offsets": _offsets_from_plate(world_point, plate_bbox) if plate_bbox else None,
    }


def _hole_data(feat, plate_bbox):
    info = {"feature_kind": "hole"}

    # Diameter
    try:
        info["hole_diameter_mm"] = _mm(feat.holeDiameter.value) if feat.holeDiameter else None
    except Exception as e:
        info["diameter_error"] = str(e)

    # Tip angle (radians in Fusion API)
    try:
        info["hole_tip_angle_rad"] = feat.tipAngle.value if feat.tipAngle else None
    except Exception:
        info["hole_tip_angle_rad"] = None

    # Extent (depth definition)
    try:
        ext = feat.extentDefinition
        info["extent_type"] = ext.objectType if ext else None
        # depth value if available
        try:
            if hasattr(ext, "distance") and ext.distance:
                info["extent_distance_mm"] = _mm(ext.distance.value)
        except Exception:
            pass
    except Exception as e:
        info["extent_error"] = str(e)

    # Position extraction — try multiple strategies, accept first that yields points
    positions = []
    strategies_tried = []

    # Strategy 1: holePositionDefinition (sketch-point based holes)
    try:
        hpd = feat.holePositionDefinition
        if hpd is not None:
            info["holePositionDefinition_type"] = hpd.objectType
            try:
                if hasattr(hpd, "sketchPoints") and hpd.sketchPoints:
                    for sp in hpd.sketchPoints:
                        positions.append(_pos_record(sp.worldGeometry, plate_bbox))
                    strategies_tried.append("hpd.sketchPoints")
            except Exception as e:
                strategies_tried.append(f"hpd.sketchPoints failed: {e}")
            try:
                if not positions and hasattr(hpd, "sketchPoint") and hpd.sketchPoint:
                    positions.append(_pos_record(hpd.sketchPoint.worldGeometry, plate_bbox))
                    strategies_tried.append("hpd.sketchPoint")
            except Exception as e:
                strategies_tried.append(f"hpd.sketchPoint failed: {e}")
    except Exception as e:
        strategies_tried.append(f"hpd access failed: {e}")

    # Strategy 2: feature faces — cylindrical face origin gives axis on hole center
    if not positions:
        try:
            for face in feat.faces:
                try:
                    geom = face.geometry
                    if geom is None:
                        continue
                    if geom.objectType == "adsk::core::Cylinder":
                        rec = _pos_record(geom.origin, plate_bbox)
                        rec["from_face"] = True
                        rec["axis"] = {"x": geom.axis.x, "y": geom.axis.y, "z": geom.axis.z}
                        rec["radius_mm"] = _mm(geom.radius)
                        positions.append(rec)
                except Exception:
                    continue
            if positions:
                strategies_tried.append("feat.faces[cylindrical].origin")
        except Exception as e:
            strategies_tried.append(f"faces failed: {e}")

    info["positions"] = positions
    info["position_strategies"] = strategies_tried
    return info


def _sketch_points(sketch, plate_bbox):
    pts = []
    try:
        for sp in sketch.sketchPoints:
            wp = sp.worldGeometry
            pts.append({
                "world": _point_dict(wp),
                "offsets": _offsets_from_plate(wp, plate_bbox) if plate_bbox else None,
            })
    except Exception as e:
        pts.append({"error": str(e)})
    return pts


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox("Kein aktives Design gefunden.")
            return

        root = design.rootComponent

        plate_bbox = None
        for body in root.bRepBodies:
            try:
                bb = body.boundingBox
                if plate_bbox is None:
                    plate_bbox = bb
                else:
                    try:
                        plate_bbox.combine(bb)
                    except Exception:
                        pass
            except Exception:
                continue

        dump = {
            "schema": "flex_features.v1",
            "user_parameters": _user_params(design),
            "plate_bbox_mm": _bbox_corners(plate_bbox) if plate_bbox else None,
            "bodies": [],
            "timeline": [],
            "holes": [],
            "sketches": [],
        }

        for body in root.bRepBodies:
            try:
                dump["bodies"].append({
                    "name": body.name,
                    "is_visible": body.isVisible,
                    "bbox_mm": _bbox_corners(body.boundingBox),
                })
            except Exception as e:
                dump["bodies"].append({"error": str(e)})

        for sk in root.sketches:
            try:
                entry = {
                    "name": sk.name,
                    "is_visible": sk.isVisible,
                    "is_construction": sk.isConstruction if hasattr(sk, "isConstruction") else None,
                    "points": _sketch_points(sk, plate_bbox),
                }
                dump["sketches"].append(entry)
            except Exception as e:
                dump["sketches"].append({"error": str(e)})

        for tl_idx in range(design.timeline.count):
            try:
                tl = design.timeline.item(tl_idx)
            except Exception as e:
                dump["timeline"].append({"index": tl_idx, "error": f"item access failed: {e}"})
                continue

            entry = {"index": tl_idx}
            try:
                entry["name"] = tl.name
            except Exception as e:
                entry["name_error"] = str(e)
            try:
                entry["is_suppressed"] = bool(tl.isSuppressed)
            except Exception:
                pass
            try:
                entry["is_rolled_back"] = bool(tl.isRolledBack)
            except Exception:
                pass

            ent = None
            try:
                ent = tl.entity
            except Exception as e:
                entry["entity_error"] = str(e)

            if ent is not None:
                try:
                    entry["type"] = ent.objectType
                except Exception:
                    entry["type"] = "unknown"
                try:
                    if isinstance(ent, adsk.fusion.HoleFeature):
                        detail = _hole_data(ent, plate_bbox)
                        entry["detail"] = detail
                        dump["holes"].append({
                            "name": entry.get("name"),
                            "is_suppressed": entry.get("is_suppressed"),
                            "data": detail,
                        })
                except Exception as e:
                    entry["detail_error"] = str(e)

            dump["timeline"].append(entry)

        # Output path: ALWAYS the repo path. Fusion runs imported scripts from
        # %APPDATA%\Autodesk\...\Scripts\, so __file__ points there — not into
        # the repo. Hardcoded absolute path keeps the JSON in sync with the .f3d.
        out_path = (
            r"E:\PRODUKTENTWICKLUNG_TPE\06_GITHUB\Test_Konfig\backend"
            r"\aps_addin\flex_table\features.json"
        )
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(dump, f, indent=2, ensure_ascii=False)

        ui.messageBox(
            f"features.json geschrieben:\n{out_path}\n\n"
            f"User-Parameter: {len(dump['user_parameters'])}\n"
            f"Timeline-Features: {len(dump['timeline'])}\n"
            f"Hole-Features: {len(dump['holes'])}\n"
            f"Sketches: {len(dump['sketches'])}"
        )

    except Exception:
        if ui:
            ui.messageBox(f"dump_fusion_features Fehler:\n{traceback.format_exc()}")
        raise
