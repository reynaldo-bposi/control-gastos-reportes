import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
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
.block-container{padding-top:2rem;padding-bottom:2rem;}
div[data-testid="stMetric"]{padding:8px 12px;background:#f8f9fa;border-radius:8px;}
div[data-testid="stMetricValue"]{font-size:20px;}
div[data-testid="stMetricLabel"]{font-size:12px;}
.mov-fecha{background:#f1f3f5;padding:4px 10px;font-size:12px;font-weight:600;
  color:#495057;border-radius:5px;margin:10px 0 0 0;}
.mov-row{display:flex;align-items:center;justify-content:space-between;
  padding:7px 10px;border-bottom:1px solid #f1f3f5;}
.mov-izq{display:flex;flex-direction:column;gap:1px;min-width:0;}
.mov-desc{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;}
.mov-cat{font-size:11px;color:#868e96;}
.mov-der{text-align:right;display:flex;flex-direction:column;gap:1px;
  white-space:nowrap;padding-left:12px;}
.mov-monto{font-size:14px;font-weight:700;}
.mov-saldo{font-size:11px;color:#868e96;}
.pos{color:#2b8a3e;}
.neg{color:#c92a2a;}
</style>
""", unsafe_allow_html=True)

MESES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "setiembre", 10: "octubre", 11: "noviembre",
    12: "diciembre",
}
DIAS = {
    0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves", 4: "viernes",
    5: "sábado", 6: "domingo",
}


def fecha_es(d, con_dia=True):
    if con_dia:
        return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month]} de {d.year}"
    return f"{d.day} de {MESES[d.month]} de {d.year}"


def fmt(v):
    return f"{v:,.2f}"


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
    """Carga una hoja detectando automáticamente la fila de encabezados."""
    gc = conectar_sheets()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(nombre_hoja)
    datos = ws.get_all_values()
    if not datos:
        return pd.DataFrame()

    # La fila de título tiene 1 sola celda con texto; la de encabezados tiene varias
    fila_enc = 0
    for i, fila in enumerate(datos[:4]):
        no_vacias = sum(1 for c in fila if str(c).strip())
        if no_vacias >= 2:
            fila_enc = i
            break

    if len(datos) <= fila_enc + 1:
        return pd.DataFrame()

    encabezados = [c.strip() for c in datos[fila_enc]]
    filas = datos[fila_enc + 1:]
    df = pd.DataFrame(filas, columns=encabezados)
    df["_RowNumber"] = range(fila_enc + 2, fila_enc + 2 + len(filas))
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


def buscar_col(df, opciones):
    """Devuelve el primer nombre de columna que exista en el DataFrame."""
    for o in opciones:
        if o in df.columns:
            return o
    return None


def mapa(df, cols_id, cols_nombre):
    """Crea un diccionario {id: nombre} a partir de una tabla maestra."""
    if df is None or df.empty:
        return {}
    ci = buscar_col(df, cols_id)
    cn = buscar_col(df, cols_nombre)
    if not ci or not cn:
        return {}
    return dict(zip(df[ci].astype(str).str.strip(), df[cn].astype(str).str.strip()))


def traducir(serie, dic):
    s = serie.astype(str).str.strip()
    return s.map(dic).fillna(s)


# ══════════════════════════════════════════
# CARGA DE DATOS
# ══════════════════════════════════════════

def cargar_opcional(nombre):
    try:
        return cargar_hoja(nombre)
    except Exception:
        return pd.DataFrame()


try:
    mov = cargar_hoja("📋 Movimientos")
    cuentas = cargar_hoja("🏦 Cuentas")
except Exception as e:
    st.error(f"Error al conectar con Google Sheets: {e}")
    st.stop()

benef = cargar_opcional("👥 Beneficiarios")
cats = cargar_opcional("🗂️ Categorías")
if cats.empty:
    cats = cargar_opcional("⚙️ Categorías")
subcats = cargar_opcional("🏷️ Subcategorías")

if mov.empty:
    st.warning("No hay movimientos registrados todavía.")
    st.stop()

mov["Fecha"] = pd.to_datetime(mov["Fecha"], dayfirst=True, errors="coerce")
mov["Monto"] = a_numero(mov["Monto"])
mov["Monto Neto"] = a_numero(mov["Monto Neto"])
mov = mov.dropna(subset=["Fecha"])

cuentas["Saldo Inicial"] = a_numero(cuentas["Saldo Inicial"])

# ── Diccionarios de traducción ID → nombre ──
d_cuentas = mapa(cuentas, ["ID"], ["Nombre Cuenta"])
d_benef = mapa(benef, ["ID"], ["Nombre / Razón Social", "Nombre"])
d_cats = mapa(cats, ["ID_Categoría", "ID"], ["Categoría", "Nombre"])
d_subs = mapa(subcats, ["ID_SubCategoría", "ID"], ["Sub Categoría", "Nombre"])

mov["Cuenta Nombre"] = traducir(mov["Cuenta"], d_cuentas)

if "Cuenta Destino" in mov.columns:
    mov["Cuenta Destino Nombre"] = traducir(mov["Cuenta Destino"], d_cuentas)

if "Beneficiario" in mov.columns:
    mov["Beneficiario Nombre"] = traducir(mov["Beneficiario"], d_benef)
else:
    mov["Beneficiario Nombre"] = ""

mov["Cat Nombre"] = traducir(mov["Categoría"], d_cats) if "Categoría" in mov.columns else ""
mov["Sub Nombre"] = traducir(mov["Sub Categ."], d_subs) if "Sub Categ." in mov.columns else ""

# ── Descripción visible ──
desc = pd.Series("", index=mov.index)
if "Tipo Mov." in mov.columns and "Cuenta Destino Nombre" in mov.columns:
    es_transf = mov["Tipo Mov."].astype(str).str.strip() == "Transferencia"
    entrada = mov["Monto Neto"] >= 0
    desc = desc.mask(
        es_transf & ~entrada, "Transferir a " + mov["Cuenta Destino Nombre"]
    )
    desc = desc.mask(
        es_transf & entrada, "Transferir desde " + mov["Cuenta Destino Nombre"]
    )
desc = desc.replace("", pd.NA).fillna(mov["Beneficiario Nombre"]).replace("", pd.NA)
mov["Desc"] = desc.fillna("(sin descripción)")

# ── Categoría / Subcategoría ──
mov["CatSub"] = (
    mov["Cat Nombre"].astype(str) + " / " + mov["Sub Nombre"].astype(str)
).str.strip(" /").str.replace(" / nan", "", regex=False)

# ══════════════════════════════════════════
# SIDEBAR — FILTROS
# ══════════════════════════════════════════

st.sidebar.markdown("### 📊 Control de gastos")

# ── Cuentas agrupadas por moneda ──
col_act = buscar_col(cuentas, ["Activa", "Activo"])
col_ord = buscar_col(cuentas, ["Orden", "orden", "N° Orden"])
col_mon = buscar_col(cuentas, ["Moneda"])

cta = cuentas.copy()
if col_act:
    cta = cta[cta[col_act].astype(str).str.strip().str.lower().isin(["sí", "si", "yes", "true"])]

if col_ord:
    cta["_ord"] = a_numero(cta[col_ord])
else:
    cta["_ord"] = range(len(cta))

prioridad = {"PEN": 0, "USD": 1}
if col_mon:
    cta["_mon"] = cta[col_mon].astype(str).str.strip().str.upper()
else:
    cta["_mon"] = "PEN"
cta["_pri"] = cta["_mon"].map(prioridad).fillna(9)
cta = cta.sort_values(["_pri", "_mon", "_ord", "Nombre Cuenta"])

opciones_cuenta = ["Todas"]
etiquetas = {"Todas": "Todas las cuentas"}
moneda_actual = None
for _, r in cta.iterrows():
    nombre = str(r["Nombre Cuenta"]).strip()
    if not nombre:
        continue
    if r["_mon"] != moneda_actual:
        moneda_actual = r["_mon"]
        sep = f"── {moneda_actual} ──"
        opciones_cuenta.append(sep)
        etiquetas[sep] = sep
    opciones_cuenta.append(nombre)
    etiquetas[nombre] = f"   {nombre}"

cuenta_sel = st.sidebar.selectbox(
    "Cuenta", opciones_cuenta, format_func=lambda x: etiquetas.get(x, x)
)
if cuenta_sel.startswith("──"):
    cuenta_sel = "Todas"

# ── Filtros rápidos de periodo ──
fecha_min = mov["Fecha"].min().date()
fecha_max = mov["Fecha"].max().date()
hoy = datetime.now().date()

periodo = st.sidebar.radio(
    "Periodo",
    ["Este mes", "Últimos 30 días", "Últimos 60 días", "Últimos 90 días",
     "Todo el historial", "Personalizado"],
    index=4,
)

if periodo == "Este mes":
    desde, hasta = hoy.replace(day=1), hoy
elif periodo == "Últimos 30 días":
    desde, hasta = hoy - timedelta(days=30), hoy
elif periodo == "Últimos 60 días":
    desde, hasta = hoy - timedelta(days=60), hoy
elif periodo == "Últimos 90 días":
    desde, hasta = hoy - timedelta(days=90), hoy
elif periodo == "Todo el historial":
    desde, hasta = fecha_min, fecha_max
else:
    rango = st.sidebar.date_input(
        "Rango de fechas",
        value=(fecha_min, fecha_max),
        min_value=fecha_min,
        max_value=fecha_max,
        format="DD/MM/YYYY",
    )
    if isinstance(rango, tuple) and len(rango) == 2:
        desde, hasta = rango
    else:
        desde, hasta = fecha_min, fecha_max

perfil_sel = st.sidebar.selectbox("Perfil", ["Todos", "Personal", "Empresa"])
tipo_sel = st.sidebar.selectbox(
    "Tipo de movimiento", ["Todos", "Egreso", "Ingreso", "Transferencia"]
)

orden_sel = st.sidebar.radio(
    "Ordenar por fecha", ["Más reciente primero", "Más antiguo primero"]
)
descendente = orden_sel == "Más reciente primero"

# ══════════════════════════════════════════
# SALDO ACUMULADO — sobre TODO el historial
# ══════════════════════════════════════════

base = mov.copy()

if cuenta_sel != "Todas":
    base = base[base["Cuenta Nombre"] == cuenta_sel]
    ids = [k for k, v in d_cuentas.items() if v == cuenta_sel]
    saldo_inicial = 0.0
    if ids:
        fila = cuentas[cuentas["ID"].astype(str).str.strip() == ids[0]]
        if not fila.empty:
            saldo_inicial = float(fila["Saldo Inicial"].iloc[0])
else:
    saldo_inicial = float(cuentas["Saldo Inicial"].sum())

base = base.sort_values(["Fecha", "_RowNumber"], ascending=[True, True])
base["Saldo Cierre"] = saldo_inicial + base["Monto Neto"].cumsum()

# ══════════════════════════════════════════
# FILTROS DE VISUALIZACIÓN
# ══════════════════════════════════════════

df = base[(base["Fecha"].dt.date >= desde) & (base["Fecha"].dt.date <= hasta)].copy()

if perfil_sel != "Todos" and "Perfil" in df.columns:
    df = df[df["Perfil"].astype(str).str.strip() == perfil_sel]

if tipo_sel != "Todos" and "Tipo Mov." in df.columns:
    df = df[df["Tipo Mov."].astype(str).str.strip() == tipo_sel]

df = df.sort_values(
    ["Fecha", "_RowNumber"], ascending=[not descendente, not descendente]
).reset_index(drop=True)

# ══════════════════════════════════════════
# HEADER Y MÉTRICAS
# ══════════════════════════════════════════

titulo = cuenta_sel if cuenta_sel != "Todas" else "Todas las cuentas"
st.markdown(f"#### Extracto — {titulo}")
st.caption(
    f"{len(df)} movimientos · {fecha_es(desde, False)} al {fecha_es(hasta, False)}"
)

ingresos = df[df["Monto Neto"] > 0]["Monto Neto"].sum()
egresos = df[df["Monto Neto"] < 0]["Monto Neto"].sum()
saldo_actual = base["Saldo Cierre"].iloc[-1] if len(base) > 0 else saldo_inicial

c1, c2, c3, c4 = st.columns(4)
c1.metric("Saldo inicial", f"S/ {fmt(saldo_inicial)}")
c2.metric("Ingresos del periodo", f"S/ {fmt(ingresos)}")
c3.metric("Egresos del periodo", f"S/ {fmt(abs(egresos))}")
c4.metric("Saldo actual", f"S/ {fmt(saldo_actual)}")

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
    height=220,
    margin=dict(l=0, r=0, t=10, b=0),
    yaxis_title="",
    xaxis_title="",
)
st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════
# LISTA DE MOVIMIENTOS
# ══════════════════════════════════════════

html = []
fecha_actual = None
for _, r in df.iterrows():
    f = fecha_es(r["Fecha"].date())
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

st.markdown("")

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

resumen = (
    df[df["Monto Neto"] < 0]
    .groupby("Cat Nombre")["Monto Neto"]
    .sum()
    .abs()
    .sort_values(ascending=True)
    .tail(10)
)
if len(resumen) > 0:
    st.markdown("##### Egresos por categoría")
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
        height=260,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="",
        yaxis_title="",
    )
    st.plotly_chart(fig2, use_container_width=True)
