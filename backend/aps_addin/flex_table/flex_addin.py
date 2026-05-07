"""
Fusion 360 Add-In: FLEX TABLE parametrische STEP-Exportierung.
Läuft headless im APS DA Worker und lokal in Fusion 360.

APS DA Worker legt bereit:
  - params.json  (workDir)
  - flex_reference.f3d  (workDir)
Erwartet als Output:
  - result.step  (workDir)

Lokaltest in Fusion:
  Werkzeuge -> Skripts und Add-Ins -> Add-Ins -> "+" -> diesen Ordner wählen -> Run
"""
import adsk.core
import adsk.fusion
import json
import os
import traceback

PARAM_MAP = {
    "breite": "Breite",
    "tiefe": "Tiefe",
    "r_ecke": "R_Ecke",
    "r_kante": "R_Kante",
    "dicke": "Dicke",
}


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        work_dir = os.path.dirname(os.path.abspath(__file__))
        params_path = os.path.join(work_dir, "params.json")
        model_path = os.path.join(work_dir, "flex_reference.f3d")
        output_path = os.path.join(work_dir, "result.step")

        with open(params_path, "r") as f:
            params = json.load(f)

        params.setdefault("dicke", 28.6)

        import_mgr = app.importManager
        options = import_mgr.createFusionArchiveImportOptions(model_path)
        doc = import_mgr.importToNewDocument(options)
        doc.activate()

        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType

        user_params = design.userParameters
        for key, fusion_name in PARAM_MAP.items():
            value_mm = params.get(key)
            if value_mm is None:
                continue
            param = user_params.itemByName(fusion_name)
            if param is None:
                raise RuntimeError(f"User Parameter '{fusion_name}' nicht gefunden. Bitte im Modell anlegen.")
            param.expression = f"{value_mm} mm"

        export_mgr = design.exportManager
        step_options = export_mgr.createSTEPExportOptions(output_path)
        export_mgr.execute(step_options)

        doc.close(False)

    except Exception:
        if ui:
            ui.messageBox(f"flex_addin Fehler:\n{traceback.format_exc()}")
        raise
