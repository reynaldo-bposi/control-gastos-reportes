"""
Control de Gastos — Streamlit App
Sistema multi-moneda para LA BPOSI con SUNAT compliance
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# ========================================
# IMPORTS DE MÓDULOS PROPIOS
# ========================================
import movimientos
import reportes
import conciliacion
import regularizaciones  # ← NUEVO MÓDULO

# ========================================
# CONFIGURACIÓN
# ========================================

st.set_page_config(
    page_title="Control de Gastos — LA BPOSI",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# IDs y credenciales
SHEET_ID = "1Wx5N3uAi-_4iLpYOibXgXisT3PizOlwDWQtAn1str_w"
GCP_PROJECT = "control-gastos-503518"
SERVICE_ACCOUNT_EMAIL = "streamlit-gastos@control-gastos-503518.iam.gserviceaccount.com"

# CSS personalizado
st.markdown("""
    <style>
        .titulo { font-size: 28px; font-weight: 700; margin-bottom: 1.5rem; color: #f0f6fc; }
        .sub { font-size: 16px; font-weight: 700; margin: 1.5rem 0 1rem; color: #c9d1d9; }
        .kpi { 
            background: #161b22; 
            border: 1px solid #30363d;
            border-radius: 8px; 
            padding: 16px; 
            text-align: center; 
        }
        .kpi-label { font-size: 11px; color: #8b949e; text-transform: uppercase; }
        .kpi-val { font-size: 20px; font-weight: 700; color: #58a6ff; }
    </style>
""", unsafe_allow_html=True)

# ========================================
# FUNCIONES DE CONEXIÓN
# ========================================

@st.cache_resource
def conectar_sheets():
    """Conecta a Google Sheets usando Service Account"""
    try:
        # Asume que tienes tus credenciales en Streamlit secrets
        creds_dict = st.secrets["google_service_account"]
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        gc = gspread.authorize(creds)
        return gc
    except Exception as e:
        st.error(f"❌ Error al conectar a Google Sheets: {str(e)}")
        return None

@st.cache_data(ttl=300)
def cargar_hoja():
    """Carga datos de Google Sheets"""
    try:
        gc = conectar_sheets()
        if gc is None:
            return pd.DataFrame()
        
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet("Movimientos")
        data = ws.get_all_records()
        
        mov = pd.DataFrame(data)
        
        # Normalizar columnas de fecha
        if "Fecha" in mov.columns:
            mov["Fecha"] = pd.to_datetime(mov["Fecha"], format="%d/%m/%Y", errors="coerce")
        if "Fecha Comprobante" in mov.columns:
            mov["Fecha Comprobante"] = pd.to_datetime(mov["Fecha Comprobante"], format="%d/%m/%Y", errors="coerce")
        
        # Agregar índice de fila para regularizaciones
        mov["_RowNumber"] = range(2, len(mov) + 2)
        
        # Normalizar moneda
        if "Moneda" in mov.columns:
            mov["_moneda_code"] = mov["Moneda"].apply(lambda x: normalizar_moneda(x))
        
        return mov
    except Exception as e:
        st.error(f"❌ Error al cargar datos: {str(e)}")
        return pd.DataFrame()

def normalizar_moneda(m):
    """Normaliza códigos de moneda"""
    s = str(m).strip().upper()
    if not s or s == "NAN":
        return "PEN"
    if any(k in s for k in ("PEN", "SOL", "S/")):
        return "PEN"
    if any(k in s for k in ("USD", "US$", "DOLAR", "DÓLAR", "DOL")):
        return "USD"
    if any(k in s for k in ("ARS", "PESO ARG")):
        return "ARS"
    return s[:3]

# ========================================
# INTERFAZ PRINCIPAL
# ========================================

st.markdown('<div style="font-size: 20px; font-weight: 700; margin-bottom: 1rem;">🎯 Control de Gastos — LA BPOSI</div>', unsafe_allow_html=True)

# Menú de navegación
nav_main = ["Movimientos", "Reportes", "Conciliación", "Regularizaciones"]  # ← AGREGADO

col_nav = st.columns(len(nav_main))
vista = None

for i, seccion in enumerate(nav_main):
    with col_nav[i]:
        if st.button(f"{'📊' if seccion == 'Movimientos' else '📈' if seccion == 'Reportes' else '✓' if seccion == 'Conciliación' else '💰'} {seccion}", use_container_width=True, key=f"nav_{seccion}"):
            st.session_state.vista_actual = seccion

vista = st.session_state.get("vista_actual", "Movimientos")

st.divider()

# Cargar datos
mov = cargar_hoja()

# ========================================
# RENDERIZAR VISTAS
# ========================================

if vista == "Movimientos":
    movimientos.render(mov, conectar_sheets, SHEET_ID)

elif vista == "Reportes":
    reportes.render(mov)

elif vista == "Conciliación":
    conciliacion.render(mov, conectar_sheets, SHEET_ID)

# ========================================
# REGULARIZACIONES — NUEVA VISTA
# ========================================
elif vista == "Regularizaciones":
    regularizaciones.render(mov, conectar_sheets, SHEET_ID)

# ========================================
# FOOTER
# ========================================

st.divider()
st.caption("Control de Gastos v2.1 • Última actualización: " + datetime.now().strftime("%d/%m/%Y %H:%M"))
