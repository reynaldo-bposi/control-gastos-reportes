import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go

# ══════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════

SHEET_ID = "1Wx5N3uAi-_4iLpYOibXgXisT3PizOlwDWQtAn1str_w"

st.set_page_config(
    page_title="Control de Gastos — Reportes",
    page_icon="📊",
    layout="wide",
)

# ══════════════════════════════════════════
# CONEXIÓN A GOOGLE SHEETS
# ══════════════════════════════════════════

@st.cache_resource
def conectar_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    return gspread.authorize(creds)


@st.cache_data(ttl=300)
def cargar_hoja(nombre_hoja):
    """Carga una hoja del Google Sheets como DataFrame."""
    gc = conectar_sheets()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(nombre_hoja)
    # Los encabezados están en la fila 2 (fila 1 es el título)
    datos = ws.get_all_values()
    if len(datos) < 2:
        return pd.DataFrame()
    encabezados = datos[0]
    filas = datos[1:]
    df = pd.DataFrame(filas, columns=encabezados)
    # Eliminar filas completamente vacías
    df = df[df.apply(lambda r: any(str(v).strip() for v in r), axis=1)]
    return df


def a_numero(serie):
    """Convierte una columna de texto a número."""
    return pd.to_numeric(
        serie.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("S/", "", regex=False)
        .str.strip()
        .replace("", "0"),
        errors="coerce",
    ).fillna(0)


# ══════════════════════════════════════════
# CARGA DE DATOS
# ══════════════════════════════════════════

try:
    mov = cargar_hoja("📋 Movimientos")
    cuentas = cargar_hoja("🏦 Cuentas")
except Exception as e:
    st.error(f"Error al conectar con Google Sheets: {e}")
    st.stop()

if mov.empty:
    st.warning("No hay movimientos registrados todavía.")
    st.stop()

st.write("Columnas encontradas:", list(mov.columns))
st.stop()

# Limpieza de datos
mov["Fecha"] = pd.to_datetime(mov["Fecha"], dayfirst=True, errors="coerce")
mov["Monto"] = a_numero(mov["Monto"])
mov["Monto Neto"] = a_numero(mov["Monto Neto"])
mov["Monto PEN"] = a_numero(mov["Monto PEN"])
mov = mov.dropna(subset=["Fecha"])

cuentas["Saldo Inicial"] = a_numero(cuentas["Saldo Inicial"])

# Mapear ID de cuenta a nombre
mapa_cuentas = dict(zip(cuentas["ID"].astype(str), cuentas["Nombre Cuenta"]))
mapa_saldo_inicial = dict(zip(cuentas["ID"].astype(str), cuentas["Saldo Inicial"]))
mov["Cuenta Nombre"] = mov["Cuenta"].astype(str).map(mapa_cuentas).fillna("(sin cuenta)")

# ══════════════════════════════════════════
# SIDEBAR — FILTROS
# ══════════════════════════════════════════

st.sidebar.markdown("### 📊 Control de gastos")
st.sidebar.markdown("---")

lista_cuentas = ["Todas"] + sorted(cuentas["Nombre Cuenta"].dropna().unique().tolist())
cuenta_sel = st.sidebar.selectbox("Cuenta", lista_cuentas)

# Rango de fechas
fecha_min = mov["Fecha"].min().date()
fecha_max = mov["Fecha"].max().date()
rango = st.sidebar.date_input(
    "Periodo",
    value=(fecha_min, fecha_max),
    min_value=fecha_min,
    max_value=fecha_max,
)

perfil_sel = st.sidebar.selectbox("Perfil", ["Todos", "Personal", "Empresa"])
tipo_sel = st.sidebar.selectbox(
    "Tipo de movimiento", ["Todos", "Egreso", "Ingreso", "Transferencia"]
)

# ══════════════════════════════════════════
# APLICAR FILTROS
# ══════════════════════════════════════════

df = mov.copy()

if cuenta_sel != "Todas":
    df = df[df["Cuenta Nombre"] == cuenta_sel]

if isinstance(rango, tuple) and len(rango) == 2:
    df = df[
        (df["Fecha"].dt.date >= rango[0]) & (df["Fecha"].dt.date <= rango[1])
    ]

if perfil_sel != "Todos" and "Perfil" in df.columns:
    df = df[df["Perfil"] == perfil_sel]

if tipo_sel != "Todos" and "Tipo Mov." in df.columns:
    df = df[df["Tipo Mov."] == tipo_sel]

df = df.sort_values("Fecha").reset_index(drop=True)

# ══════════════════════════════════════════
# SALDO ACUMULADO
# ══════════════════════════════════════════

if cuenta_sel != "Todas":
    id_cuenta = [k for k, v in mapa_cuentas.items() if v == cuenta_sel]
    saldo_inicial = mapa_saldo_inicial.get(id_cuenta[0], 0) if id_cuenta else 0
else:
    saldo_inicial = cuentas["Saldo Inicial"].sum()

df["Saldo Cierre"] = saldo_inicial + df["Monto Neto"].cumsum()

# ══════════════════════════════════════════
# HEADER Y MÉTRICAS
# ══════════════════════════════════════════

titulo = f"Extracto — {cuenta_sel}" if cuenta_sel != "Todas" else "Extracto — Todas las cuentas"
st.markdown(f"## {titulo}")
st.caption(f"{len(df)} movimientos · {rango[0].strftime('%d/%m/%Y')} al {rango[1].strftime('%d/%m/%Y')}" if isinstance(rango, tuple) and len(rango) == 2 else f"{len(df)} movimientos")

col1, col2, col3, col4 = st.columns(4)

ingresos = df[df["Monto Neto"] > 0]["Monto Neto"].sum()
egresos = df[df["Monto Neto"] < 0]["Monto Neto"].sum()
neto = df["Monto Neto"].sum()
saldo_final = df["Saldo Cierre"].iloc[-1] if len(df) > 0 else saldo_inicial

col1.metric("Saldo inicial", f"S/ {saldo_inicial:,.2f}")
col2.metric("Ingresos", f"S/ {ingresos:,.2f}")
col3.metric("Egresos", f"S/ {abs(egresos):,.2f}")
col4.metric("Saldo final", f"S/ {saldo_final:,.2f}", delta=f"{neto:,.2f}")

st.markdown("---")

# ══════════════════════════════════════════
# GRÁFICO DE EVOLUCIÓN
# ══════════════════════════════════════════

if len(df) > 0:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["Fecha"],
            y=df["Saldo Cierre"],
            mode="lines+markers",
            name="Saldo",
            line=dict(color="#1565C0", width=2),
            marker=dict(size=6),
        )
    )
    fig.update_layout(
        title="Evolución del saldo",
        xaxis_title="",
        yaxis_title="Saldo (S/)",
        height=280,
        margin=dict(l=0, r=0, t=40, b=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════
# TABLA DE MOVIMIENTOS
# ══════════════════════════════════════════

st.markdown("### Detalle de movimientos")

columnas_mostrar = [
    "Fecha",
    "Cuenta Nombre",
    "Descripcion Transferencia",
    "Perfil",
    "Tipo Mov.",
    "Monto Neto",
    "Saldo Cierre",
    "Estado",
]
columnas_existentes = [c for c in columnas_mostrar if c in df.columns]

df_vista = df[columnas_existentes].copy()
df_vista["Fecha"] = df_vista["Fecha"].dt.strftime("%d/%m/%Y")

# Formato de colores
def colorear(val):
    try:
        v = float(val)
        if v < 0:
            return "color: #e53935"
        elif v > 0:
            return "color: #43a047"
    except (ValueError, TypeError):
        pass
    return ""


st.dataframe(
    df_vista.style.map(colorear, subset=[c for c in ["Monto Neto", "Saldo Cierre"] if c in df_vista.columns])
    .format({
        "Monto Neto": "S/ {:,.2f}",
        "Saldo Cierre": "S/ {:,.2f}",
    }),
    use_container_width=True,
    height=420,
)

# ══════════════════════════════════════════
# EXPORTAR
# ══════════════════════════════════════════

st.markdown("---")

csv = df_vista.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    label="📥 Descargar reporte (CSV)",
    data=csv,
    file_name=f"extracto_{cuenta_sel.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv",
)

# ══════════════════════════════════════════
# RESUMEN POR CATEGORÍA
# ══════════════════════════════════════════

if "Categoría" in df.columns and len(df) > 0:
    st.markdown("### Resumen por categoría")
    resumen = (
        df[df["Monto Neto"] < 0]
        .groupby("Categoría")["Monto Neto"]
        .sum()
        .abs()
        .sort_values(ascending=False)
        .head(10)
    )
    if len(resumen) > 0:
        fig2 = go.Figure(
            go.Bar(
                x=resumen.values,
                y=resumen.index,
                orientation="h",
                marker_color="#1565C0",
            )
        )
        fig2.update_layout(
            xaxis_title="Monto (S/)",
            yaxis_title="",
            height=300,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig2, use_container_width=True)
