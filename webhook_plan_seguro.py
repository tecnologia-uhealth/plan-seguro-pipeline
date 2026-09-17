# -*- coding: utf-8 -*-
"""
Servidor Flask que recibe la llamada del cron de Odoo, orquesta:
generar Excel "Lista de Asegurados" (con TODOS los asegurados del grupo)
-> generar PDF "Orden de Trabajo" (solo con la 1ra persona como ejemplo,
si son varios) -> correr el RPA contra el portal de Plan Seguro.

Mismo patrón que webhook_odoo.py (Thona), corre en el mismo VPS/EasyPanel.

Soporta cualquier cantidad de asegurados por trámite (confirmado por
Carlos, ver generar_orden_trabajo.py) — recibe una LISTA de asegurados,
no uno solo.
"""

import os
import base64
import logging
from flask import Flask, request, jsonify

from generar_excel_plan_seguro import generar_excel_plan_seguro
from generar_orden_trabajo import generar_orden_trabajo
from rpa_plan_seguro import emitir_movimiento_plan_seguro, RPAError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("webhook_plan_seguro")

app = Flask(__name__)

TRABAJO_DIR = os.environ.get("TRABAJO_DIR", "/tmp/plan_seguro_pipeline")
os.makedirs(TRABAJO_DIR, exist_ok=True)

WEBHOOK_SECRET = os.environ.get("PLAN_SEGURO_WEBHOOK_SECRET", "")


@app.route("/webhook/plan_seguro/alta", methods=["POST"])
def webhook_plan_seguro():
    if WEBHOOK_SECRET:
        recibido = request.headers.get("X-Webhook-Secret", "")
        if recibido != WEBHOOK_SECRET:
            return jsonify({"ok": False, "error": "Secreto inválido"}), 403

    payload = request.get_json(force=True)

    try:
        orden_id = payload["order_id"]
        tipo_movimiento = payload.get("tipo_movimiento", "alta")
        no_poliza = payload["no_poliza"]
        correo_contratante_aprobacion = payload.get("correo_contratante_aprobacion", "gmm@grupocyse.com")
        asegurados = payload["asegurados"]  # LISTA — puede ser 1 o varios

        if not asegurados:
            return jsonify({"ok": False, "error": "No se recibió ningún asegurado."}), 400

        base = f"{TRABAJO_DIR}/orden_{orden_id}_{tipo_movimiento}"

        # 1. Generar Excel "Lista de Asegurados" — lleva a TODOS, sin límite
        excel_asegurados = [
            {
                "nombre_completo": f"{a['nombre']} {a['apellido_paterno']} {a.get('apellido_materno', '')}".strip(),
                "fecha_nacimiento": a["fecha_nacimiento"],
                "sexo": a.get("sexo_completo") or ("Masculino" if a["sexo"] == "M" else "Femenino"),
                "parentesco": a.get("parentesco", ""),
            }
            for a in asegurados
        ]
        excel_path = generar_excel_plan_seguro(
            excel_asegurados,
            no_poliza=no_poliza,
            salida=f"{base}_lista_asegurados.xlsx",
        )

        pdf_path = None
        if tipo_movimiento == "alta":
            # 2. Generar PDF "Orden de Trabajo" — SOLO para alta. Si son
            # varios asegurados, solo se usa el primero como fila de
            # ejemplo (el Excel ya lleva a todos — ver nota en
            # generar_orden_trabajo.py).
            pdf_asegurados = [
                {
                    "nombre": a["nombre"],
                    "apellido_paterno": a["apellido_paterno"],
                    "apellido_materno": a.get("apellido_materno", ""),
                    "fecha_nacimiento": a["fecha_nacimiento"],
                    "sexo": a["sexo"],
                    "parentesco": a.get("parentesco", ""),
                }
                for a in asegurados
            ]
            pdf_path = generar_orden_trabajo(
                pdf_asegurados,
                no_poliza=no_poliza,
                salida=f"{base}_orden_trabajo.pdf",
            )

        # 3. Correr el RPA
        emitir_movimiento_plan_seguro(
            no_poliza=no_poliza,
            tipo_movimiento=tipo_movimiento,
            lista_asegurados_path=excel_path,
            orden_trabajo_path=pdf_path,  # None para baja, la función lo ignora
            correo_contratante_aprobacion=correo_contratante_aprobacion,
            # La identificación oficial solo aplica para alta, y solo se
            # manda la de la primera persona (misma lógica que el PDF).
            ine_base64=payload.get("ine_base64") if tipo_movimiento == "alta" else None,
            ine_nombre_archivo=payload.get("ine_nombre_archivo", "identificacion.pdf"),
        )

        log.info(
            f"Orden {orden_id}: {tipo_movimiento} registrada en Plan Seguro para "
            f"{len(asegurados)} asegurado(s) en 1 trámite (pendiente aprobación manual)"
        )

        # Regresar los archivos generados para que Odoo los adjunte a la
        # orden (así Carlos puede verlos sin entrar al servidor).
        with open(excel_path, "rb") as f:
            excel_base64 = base64.b64encode(f.read()).decode()

        pdf_base64 = None
        if pdf_path:
            with open(pdf_path, "rb") as f:
                pdf_base64 = base64.b64encode(f.read()).decode()

        return jsonify({
            "ok": True,
            "excel_base64": excel_base64,
            "excel_filename": os.path.basename(excel_path),
            "pdf_base64": pdf_base64,
            "pdf_filename": os.path.basename(pdf_path) if pdf_path else None,
        }), 200

    except RPAError as e:
        log.exception("Error del RPA en Plan Seguro")
        screenshot_path = None
        if e.screenshot_base64:
            screenshot_path = f"{TRABAJO_DIR}/error_screenshot_{orden_id if 'orden_id' in dir() else 'x'}.png"
            try:
                with open(screenshot_path, "wb") as f:
                    f.write(base64.b64decode(e.screenshot_base64))
            except Exception:
                screenshot_path = None
        return jsonify({
            "ok": False,
            "error": str(e),
            "screenshot_base64": e.screenshot_base64,  # decodificable para ver qué pasaba
            "screenshot_guardado_en_servidor": screenshot_path,
        }), 500

    except Exception as e:
        log.exception("Error procesando movimiento Plan Seguro")
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)
