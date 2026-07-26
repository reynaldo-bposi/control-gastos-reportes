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

st.markdown("""
<style>
.mov-fecha{background:#f1f3f5;padding:6px 12px;font-size:13px;font-weight:600;
  color:#495057;border-radius:6px;margin:14px 0 4px 0;}
.mov-row{display:flex;align-items:center;justify-content:space-between;
  padding:10px 12px;border-bottom:1px solid #e9ecef;}
.mov-izq{display:flex;flex-direction:column;gap:2px;}
.mov-desc{font-size:15px;font-weight:600;}
.mov-cat{font-size:12px;color:#868e96;}
.mov-der{text-align:right;display:flex;flex-direction:column;gap:2px;}
.mov-monto{font-size:15px;font-weight:700;}
.mov-saldo{font-size:12px;color:#868e96;}
.pos{color:#2b8a3e;}
.neg{color:#c92a2a;}
</style>
""", unsafe_allow_html=True)

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
def cargar_hoja(nombre_hoja, fila_encabezado=0):
    gc = conectar_sheets()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(nombre_hoja)
    datos = ws.get_all_values()
    if len(datos) <= fila_encabezado + 1:
        return pd.DataFrame()
    encabezados = datos[fila_encabezado]
    filas = datos[fila_encabezado + 1:]
    df = pd.DataFrame(filas, columns=encabezados)
    df["_RowNumber"] = range(fila_encabezado + 2, fila_encabezado + 2 + len(filas))
    df = df[df.apply(lambda r: any(str(v).strip() for v in r), axis=1)]
    return df


def a_numero(serie):
    return pd.to_numeric(
        serie.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("S/", "", regex=False)
        .str.strip()
        .replace("", "0"),
        errors="coerce",
    ).fillna(0)


def fmt(v):
    return f"{v:,.2f}"


# ══════════════════════════════════════════
# CARGA DE DATOS
# ══════════════════════════════════════════

try:
    mov = cargar_hoja("📋 Movimientos", fila_encabezado=0)
    cuentas = cargar_hoja("🏦 Cuentas", fila_encabezado=1)
except Exception as e:
    st.error(f"Error al conectar con Google Sheets: {e}")
    st.stop()

if mov.empty:
    st.warning("No hay movimientos registrados todavía.")
    st.stop()

mov["Fecha"] = pd.to_datetime(mov["Fecha"], dayfirst=True, errors="coerce")
mov["Monto"] = a_numero(mov["Monto"])
mov["Monto Neto"] = a_numero(mov["Monto Neto"])
mov = mov.dropna(subset=["Fecha"])

cuentas["Saldo Inicial"] = a_numero(cuentas["Saldo Inicial"])

mapa_cuentas = dict(zip(cuentas["ID"].astype(str), cuentas["Nombre Cuenta"]))
mapa_saldo_ini = dict(zip(cuentas["ID"].astype(str), cuentas["Saldo Inicial"]))
mov["Cuenta Nombre"] = mov["Cuenta"].astype(str).map(mapa_cuentas).fillna("(sin cuenta)")

if "Descripcion Transferencia" in mov.columns:
    mov["Desc"] = mov["Descripcion Transferencia"].replace("", pd.NA)
else:
    mov["Desc"] = pd.NA
if "Beneficiario" in mov.columns:
    mov["Desc"] = mov["Desc"].fillna(mov["Beneficiario"])
mov["Desc"] = mov["Desc"].fillna("(sin descripción)")

cat = mov["Categoría"].astype(str) if "Categoría" in mov.columns else ""
sub = mov["Sub Categ."].astype(str) if "Sub Categ." in mov.columns else ""
mov["CatSub"] = (cat + " / " + sub).str.strip(" /")

# ══════════════════════════════════════════
# SIDEBAR — FILTROS
# ══════════════════════════════════════════

st.sidebar.markdown("### 📊 Control de gastos")
st.sidebar.markdown("---")

lista_cuentas = ["Todas"] + sorted(cuentas["Nombre Cuenta"].dropna().unique().tolist())
cuenta_sel = st.sidebar.selectbox("Cuenta", lista_cuentas)

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
# SALDO ACUMULADO — sobre TODO el historial
# ══════════════════════════════════════════

base = mov.copy()

if cuenta_sel != "Todas":
    base = base[base["Cuenta Nombre"] == cuenta_sel]
    ids = [k for k, v in mapa_cuentas.items() if v == cuenta_sel]
    saldo_inicial = mapa_saldo_ini.get(ids[0], 0) if ids else 0
else:
    saldo_inicial = cuentas["Saldo Inicial"].sum()

base = base.sort_values(["Fecha", "_RowNumber"], ascending=[True, True])
base["Saldo Cierre"] = saldo_inicial + base["Monto Neto"].cumsum()

# ══════════════════════════════════════════
# FILTROS DE VISUALIZACIÓN
# ══════════════════════════════════════════

df = base.copy()

if isinstance(rango, tuple) and len(rango) == 2:
    df = df[(df["Fecha"].dt.date >= rango[0]) & (df["Fecha"].dt.date <= rango[1])]

if perfil_sel != "Todos" and "Perfil" in df.columns:
    df = df[df["Perfil"] == perfil_sel]

if tipo_sel != "Todos" and "Tipo Mov." in df.columns:
    df = df[df["Tipo Mov."] == tipo_sel]

df = df.sort_values(["Fecha", "_RowNumber"], ascending=[False, False]).reset_index(drop=True)

# ══════════════════════════════════════════
# HEADER Y MÉTRICAS
# ══════════════════════════════════════════

titulo = f"Extracto — {cuenta_sel}" if cuenta_sel != "Todas" else "Extracto — Todas las cuentas"
st.markdown(f"## {titulo}")
if isinstance(rango, tuple) and len(rango) == 2:
    st.caption(
        f"{len(df)} movimientos · {rango[0].strftime('%d/%m/%Y')} al {rango[1].strftime('%d/%m/%Y')}"
    )

ingresos = df[df["Monto Neto"] > 0]["Monto Neto"].sum()
egresos = df[df["Monto Neto"] < 0]["Monto Neto"].sum()
saldo_actual = base["Saldo Cierre"].iloc[-1] if len(base) > 0 else saldo_inicial

c1, c2, c3, c4 = st.columns(4)
c1.metric("Saldo inicial", f"S/ {fmt(saldo_inicial)}")
c2.metric("Ingresos del periodo", f"S/ {fmt(ingresos)}")
c3.metric("Egresos del periodo", f"S/ {fmt(abs(egresos))}")
c4.metric("Saldo actual", f"S/ {fmt(saldo_actual)}")

st.markdown("---")

if len(df) == 0:
    st.info("No hay movimientos en el periodo seleccionado.")
    st.stop()

# ══════════════════════════════════════════
# GRÁFICO DE EVOLUCIÓN
# ══════════════════════════════════════════

graf = df.sort_values(["Fecha", "_RowNumber"])
fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=graf["Fecha"],
        y=graf["Saldo Cierre"],
        mode="lines",
        line=dict(color="#1565C0", width=2),
        hovertemplate="%{x|%d/%m/%Y}<br>S/ %{y:,.2f}<extra></extra>",
    )
)
fig.update_layout(
    title="Evolución del saldo",
    height=260,
    margin=dict(l=0, r=0, t=40, b=0),
    yaxis_title="",
    xaxis_title="",
)
st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════
# LISTA DE MOVIMIENTOS (estilo AppSheet)
# ══════════════════════════════════════════

st.markdown("### Movimientos")

html = []
fecha_actual = None
for _, r in df.iterrows():
    f = r["Fecha"].strftime("%d/%m/%Y")
    if f != fecha_actual:
        html.append(f'<div class="mov-fecha">{f}</div>')
        fecha_actual = f
    signo = "pos" if r["Monto Neto"] >= 0 else "neg"
    monto = f"{'+' if r['Monto Neto'] >= 0 else '-'}S/ {fmt(abs(r['Monto Neto']))}"
    cuenta_txt = f" · {r['Cuenta Nombre']}" if cuenta_sel == "Todas" else ""
    html.append(
        f'<div class="mov-row">'
        f'<div class="mov-izq">'
        f'<span class="mov-desc {signo}">{r["Desc"]}</span>'
        f'<span class="mov-cat">{r["CatSub"]}{cuenta_txt}</span>'
        f'</div>'
        f'<div class="mov-der">'
        f'<span class="mov-monto {signo}">{monto}</span>'
        f'<span class="mov-saldo">Saldo: S/ {fmt(r["Saldo Cierre"])}</span>'
        f'</div></div>'
    )

st.markdown("".join(html), unsafe_allow_html=True)

# ══════════════════════════════════════════
# EXPORTAR
# ══════════════════════════════════════════

st.markdown("---")

exportar = df[["Fecha", "Cuenta Nombre", "Desc", "CatSub", "Monto Neto", "Saldo Cierre"]].copy()
exportar["Fecha"] = exportar["Fecha"].dt.strftime("%d/%m/%Y")
exportar.columns = ["Fecha", "Cuenta", "Descripción", "Categoría", "Monto", "Saldo cierre"]

csv = exportar.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    label="📥 Descargar reporte (CSV)",
    data=csv,
    file_name=f"extracto_{cuenta_sel.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv",
)

# ══════════════════════════════════════════
# RESUMEN POR CATEGORÍA
# ══════════════════════════════════════════

if "Categoría" in df.columns:
    resumen = (
        df[df["Monto Neto"] < 0]
        .groupby("Categoría")["Monto Neto"]
        .sum()
        .abs()
        .sort_values(ascending=True)
        .tail(10)
    )
    if len(resumen) > 0:
        st.markdown("### Egresos por categoría")
        fig2 = go.Figure(
            go.Bar(
                x=resumen.values,
                y=resumen.index,
                orientation="h",
                marker_color="#1565C0",
                hovertemplate="S/ %{x:,.2f}<extra></extra>",
            )
        )
        fig2.update_layout(
            height=300,
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis_title="",
            yaxis_title="",
        )
        st.plotly_chart(fig2, use_container_width=True)
