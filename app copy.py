from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import pdfplumber
import pandas as pd
import re
import io

app = Flask(__name__)
CORS(app)

# ==========================================
# LÓGICA DE EXTRACCIÓN (Tu algoritmo base)
# ==========================================

def limpiar_espacios(texto: str) -> str:
    return " ".join(texto.split())

def obtener_cabecera(pdf):
    page0 = pdf.pages[0]
    txt = page0.extract_text() or ""
    lineas = [l.strip() for l in txt.split("\n") if l.strip()]

    if not lineas: return "", "", "", "", "", ""

    empresa = lineas[0].strip()
    direccion = lineas[1].strip() if len(lineas) > 1 else ""

    titulo = ""
    for l in lineas:
        if "MANIFIESTO DE GUIAS" in l.upper():
            titulo = l.strip()
            break

    nro_reparto = vehiculo = chofer = ""
    for l in lineas:
        if "NRO REPARTO" in l and "VEHICULO" in l and "CHOFER" in l:
            cab = l
            m_rep = re.search(r"NRO REPARTO\s*([0-9]+)", cab)
            if m_rep: nro_reparto = m_rep.group(1)
            
            m_veh = re.search(r"VEHICULO\s*([A-Z0-9\-]+)", cab)
            if m_veh: vehiculo = m_veh.group(1)
            
            parts_chofer = cab.split("CHOFER", 1)
            if len(parts_chofer) > 1:
                chofer = parts_chofer[1].strip()
            break

    return empresa, direccion, titulo, nro_reparto, vehiculo, chofer

def parsear_columna(texto_columna, base):
    registros = []
    lineas = [l.rstrip() for l in texto_columna.split("\n") if l.strip()]
    i = 0

    while i < len(lineas):
        linea = lineas[i].upper()
        if linea.startswith("NRO GUIA REMISIÓN"):
            if i + 7 >= len(lineas): break 
            
            valores = lineas[i+1].strip()
            m_guia = re.search(r"(T\d{3}-\d+)", valores)
            m_fecha = re.search(r"(\d{2}/\d{2}/\d{4})", valores)
            nro_guia = m_guia.group(1) if m_guia else ""
            fecha_traslado = m_fecha.group(1) if m_fecha else ""

            dest_line = lineas[i+3].strip()
            dni = dest_line[:8].strip()
            nombre = limpiar_espacios(dest_line[8:].strip())

            punto_line = lineas[i+5].strip()
            punto_entrega = limpiar_espacios(punto_line)

            peso_line = lineas[i+7].strip()
            peso = peso_line.replace(",", ".").strip()

            reg = {
                **base,
                "nro_guia": nro_guia,
                "fecha_traslado": fecha_traslado,
                "dni_destinatario": dni,
                "nombre_destinatario": nombre,
                "punto_entrega": punto_entrega,
                "peso": peso,
            }
            registros.append(reg)
            i += 8
            continue
        i += 1
    return registros

def procesar_pdf_bytes(file_bytes):
    todos_registros = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        empresa, direccion, titulo, nro_reparto, vehiculo, chofer = obtener_cabecera(pdf)
        # Normalizamos las claves del diccionario base para facilitar el uso en JS
        base = {
            "empresa": empresa, 
            "direccion": direccion, 
            "nro_reparto": nro_reparto, 
            "vehiculo": vehiculo, 
            "chofer": chofer,
        }
        for page in pdf.pages:
            w = page.width
            h = page.height
            mid = w / 2
            
            left = page.crop((0, 0, mid, h))
            txt_left = left.extract_text()
            if txt_left: todos_registros.extend(parsear_columna(txt_left, base))

            right = page.crop((mid, 0, w, h))
            txt_right = right.extract_text()
            if txt_right: todos_registros.extend(parsear_columna(txt_right, base))
            
    return todos_registros

# ==========================================
# RUTAS DE LA API
# ==========================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_files():
    if 'files' not in request.files:
        return jsonify({"error": "No se enviaron archivos"}), 400

    files = request.files.getlist('files')
    datos_totales = []

    for file in files:
        if file.filename.lower().endswith('.pdf'):
            try:
                file_bytes = file.read()
                datos = procesar_pdf_bytes(file_bytes)
                datos_totales.extend(datos)
            except Exception as e:
                print(f"Error procesando {file.filename}: {e}")

    return jsonify(datos_totales)

@app.route('/api/download-excel', methods=['POST'])
def download_excel():
    data = request.json
    if not data:
        return jsonify({"error": "No hay datos para generar Excel"}), 400

    # Convertir JSON a DataFrame
    df = pd.DataFrame(data)
    
    # Mapeo de columnas para el Excel final (Estética)
    mapa_columnas = {
        "nro_reparto": "Nro Reparto",
        "vehiculo": "Vehículo",
        "chofer": "Chofer",
        "nro_guia": "Guía Remisión",
        "fecha_traslado": "Fecha",
        "dni_destinatario": "DNI",
        "nombre_destinatario": "Destinatario",
        "punto_entrega": "Punto Entrega",
        "peso": "Peso (kg)"
    }
    
    # Renombrar solo las que existan
    df.rename(columns=mapa_columnas, inplace=True)
    
    # Seleccionar orden de columnas si existen
    cols_orden = [c for c in mapa_columnas.values() if c in df.columns]
    if cols_orden:
        df = df[cols_orden]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte Filtrado')
        
        # Ajustar ancho de columnas automáticamente
        worksheet = writer.sheets['Reporte Filtrado']
        for column in df:
            column_width = max(df[column].astype(str).map(len).max(), len(str(column))) + 2
            col_idx = df.columns.get_loc(column)
            worksheet.column_dimensions[chr(65 + col_idx)].width = column_width

    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='Reporte_Gestion_Logistica.xlsx'
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)