import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# ══════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════

SHEET_ID = "1Wx5N3uAi-_4iLpYOibXgXisT3PizOlwDWQtAn1str_w"

st.set_page_config(
    page_title="Movimientos",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.block-container{padding-top:3rem;padding-bottom:2rem;max-width:900px;}
section[data-testid="stSidebar"]{display:none;}

div[data-testid="stHorizontalBlock"]{flex-wrap:nowrap !important;gap:8px !important;}
div[data-testid="stColumn"]{min-width:0 !important;}
div[data-testid="stColumn"] label{font-size:11px !important;}
div[data-baseweb="select"] > div{font-size:13px;}

.titulo{font-size:22px;font-weight:700;line-height:1.4;padding:2px 0 10px 0;}

.kpi{background:#f8f9fa;border-radius:10px;padding:9px 12px;text-align:center;}
.kpi-label{font-size:10px;color:#868e96;text-transform:uppercase;
  letter-spacing:.4px;margin-bottom:2px;}
.kpi-val{font-size:18px;font-weight:700;}
.kpi-doble{font-size:15px;font-weight:700;display:flex;flex-wrap:wrap;
  justify-content:center;align-items:baseline;gap:2px 10px;}
.kpi-doble span{white-space:nowrap;}

div[data-testid="stButton"] button{height:28px;min-height:28px;border-radius:6px;
  background:#f8f9fa;border:1px solid #e9ecef;font-size:12px;
  padding:0 8px;line-height:1;}
div[data-testid="stPopover"] button{height:38px;min-height:38px;font-size:12px;
  border-radius:8px;}
.lbl-cal{font-size:11px;color:#31333f;margin-bottom:5px;}
.fila-orden{font-size:12px;color:#868e96;padding-top:6px;}

.mov-fecha{background:#f1f3f5;padding:4px 10px;font-size:12px;font-weight:600;
  color:#495057;border-radius:5px;margin:12px 0 0 0;}
.mov-row{display:flex;align-items:center;justify-content:space-between;
  padding:7px 10px;border-bottom:1px solid #f1f3f5;}
.mov-izq{display:flex;flex-direction:column;gap:1px;min-width:0;}
.mov-desc{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;}
.mov-cat{font-size:11px;color:#868e96;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;}
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
ACTIVOS = ["sí", "si", "yes", "true", "activo", "activa"]


def fecha_es(d, con_dia=True):
    if con_dia:
        return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month]} de {d.year}"
    return f"{d.day} {MESES[d.month][:3]} {d.year}"


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
    gc = conectar_sheets()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(nombre_hoja)
    datos = ws.get_all_values()
    if not datos:
        return pd.DataFrame()

    fila_enc = 0
    for i, fila in enumerate(datos[:4]):
        if sum(1 for c in fila if str(c).strip()) >= 2:
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
    for o in opciones:
        if o in df.columns:
            return o
    return None


def mapa(df, cols_id, cols_nombre):
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


def cargar_opcional(nombre):
    try:
        return cargar_hoja(nombre)
    except Exception:
        return pd.DataFrame()


@st.dialog("📅 Rango de fechas")
def dialogo_fechas(fmin, fmax):
    actual = st.session_state.get("rango_custom", (fmin, fmax))
    r = st.date_input(
        "Selecciona la fecha de inicio y la de fin",
        value=actual,
        min_value=fmin,
        max_value=fmax,
        format="DD/MM/YYYY",
        key="cal_dialogo",
    )
    c1, c2 = st.columns(2)
    if c1.button("Aplicar", use_container_width=True, type="primary"):
        if isinstance(r, tuple) and len(r) == 2:
            st.session_state["rango_custom"] = r
        st.rerun()
    if c2.button("Cancelar", use_container_width=True):
        st.rerun()


# ══════════════════════════════════════════
# CARGA DE DATOS
# ══════════════════════════════════════════

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
proyectos = cargar_opcional("📁 Proyectos")

if mov.empty:
    st.warning("No hay movimientos registrados todavía.")
    st.stop()

mov["Fecha"] = pd.to_datetime(mov["Fecha"], dayfirst=True, errors="coerce")
mov["Monto"] = a_numero(mov["Monto"])
mov["Monto Neto"] = a_numero(mov["Monto Neto"])
mov = mov.dropna(subset=["Fecha"])

cuentas["Saldo Inicial"] = a_numero(cuentas["Saldo Inicial"])

d_cuentas = mapa(cuentas, ["ID"], ["Nombre Cuenta"])
d_benef = mapa(benef, ["ID"], ["Nombre / Razón Social", "Nombre"])
d_cats = mapa(cats, ["ID_Categoría", "ID"], ["Categoría", "Nombre"])
d_subs = mapa(subcats, ["ID_SubCategoría", "ID"], ["Sub Categoría", "Nombre"])
d_proy = mapa(proyectos, ["ID"], ["Nombre Proyecto", "Nombre"])

mov["Cuenta Nombre"] = traducir(mov["Cuenta"], d_cuentas)
if "Cuenta Destino" in mov.columns:
    mov["Cuenta Destino Nombre"] = traducir(mov["Cuenta Destino"], d_cuentas)
mov["Beneficiario Nombre"] = (
    traducir(mov["Beneficiario"], d_benef) if "Beneficiario" in mov.columns else ""
)
mov["Cat Nombre"] = traducir(mov["Categoría"], d_cats) if "Categoría" in mov.columns else ""
mov["Sub Nombre"] = traducir(mov["Sub Categ."], d_subs) if "Sub Categ." in mov.columns else ""
mov["Proyecto Nombre"] = (
    traducir(mov["Proyecto"], d_proy) if "Proyecto" in mov.columns else ""
)

desc = pd.Series("", index=mov.index)
if "Tipo Mov." in mov.columns and "Cuenta Destino Nombre" in mov.columns:
    es_transf = mov["Tipo Mov."].astype(str).str.strip() == "Transferencia"
    entrada = mov["Monto Neto"] >= 0
    desc = desc.mask(es_transf & ~entrada, "Transferir a " + mov["Cuenta Destino Nombre"])
    desc = desc.mask(es_transf & entrada, "Transferir desde " + mov["Cuenta Destino Nombre"])
desc = desc.replace("", pd.NA).fillna(mov["Beneficiario Nombre"]).replace("", pd.NA)
mov["Desc"] = desc.fillna("(sin descripción)")

mov["CatSub"] = (
    mov["Cat Nombre"].astype(str) + " / " + mov["Sub Nombre"].astype(str)
).str.strip(" /").str.replace(" / nan", "", regex=False)

# ══════════════════════════════════════════
# TÍTULO + TOGGLE ACTIVOS
# ══════════════════════════════════════════

t1, t2 = st.columns([3, 1.6])
with t1:
    st.markdown('<div class="titulo">📊 Movimientos</div>', unsafe_allow_html=True)
with t2:
    solo_activos = st.toggle("Solo activos", value=True)

# ══════════════════════════════════════════
# LISTAS DE CUENTAS Y PROYECTOS
# ══════════════════════════════════════════

col_act = buscar_col(cuentas, ["Activa", "Activo"])
col_ord = buscar_col(cuentas, ["Orden", "orden", "N° Orden"])
col_mon = buscar_col(cuentas, ["Moneda"])

cta = cuentas.copy()
if solo_activos and col_act:
    cta = cta[cta[col_act].astype(str).str.strip().str.lower().isin(ACTIVOS)]
cta["_ord"] = a_numero(cta[col_ord]) if col_ord else range(len(cta))
cta["_mon"] = cta[col_mon].astype(str).str.strip().str.upper() if col_mon else "PEN"
cta["_pri"] = cta["_mon"].map({"PEN": 0, "USD": 1}).fillna(9)
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

# Proyectos
opciones_proy = ["Todos"]
if not proyectos.empty:
    col_est_p = buscar_col(proyectos, ["Estado", "Activo", "Activa"])
    col_nom_p = buscar_col(proyectos, ["Nombre Proyecto", "Nombre"])
    prj = proyectos.copy()
    if solo_activos and col_est_p:
        prj = prj[prj[col_est_p].astype(str).str.strip().str.lower().isin(ACTIVOS)]
    if col_nom_p:
        opciones_proy += sorted(
            [n for n in prj[col_nom_p].astype(str).str.strip().unique() if n]
        )

fecha_min = mov["Fecha"].min().date()
fecha_max = mov["Fecha"].max().date()
hoy = datetime.now().date()

# ══════════════════════════════════════════
# FILTROS
# ══════════════════════════════════════════

OPCIONES_PERIODO = [
    "Este mes", "Mes anterior", "Últimos 30 días", "Últimos 60 días",
    "Últimos 90 días", "Todo el historial", "Personalizado",
]

periodo_prev = st.session_state.get("periodo_sel", "Todo el historial")

# ── Primera línea: Cuenta | Proyecto ──
f1, f2 = st.columns(2)
with f1:
    cuenta_sel = st.selectbox(
        "Cuenta", opciones_cuenta, format_func=lambda x: etiquetas.get(x, x)
    )
with f2:
    proyecto_sel = st.selectbox("Proyecto", opciones_proy)

# ── Segunda línea: Periodo | Perfil | Tipo ──
g1, g2, g3 = st.columns([1.8, 1.3, 1.3])

with g1:
    periodo = st.selectbox(
        "Periodo", OPCIONES_PERIODO,
        index=OPCIONES_PERIODO.index(periodo_prev)
        if periodo_prev in OPCIONES_PERIODO else 5,
        key="periodo_sel",
    )
with g2:
    perfil_sel = st.selectbox("Perfil", ["Todos", "Personal", "Empresa"])
with g3:
    tipo_sel = st.selectbox("Tipo", ["Todos", "Egreso", "Ingreso", "Transferencia"])

if cuenta_sel.startswith("──"):
    cuenta_sel = "Todas"

# ── Rango de fechas ──
primero_mes = hoy.replace(day=1)
fin_mes_ant = primero_mes - timedelta(days=1)
ini_mes_ant = fin_mes_ant.replace(day=1)

if periodo == "Este mes":
    desde, hasta = primero_mes, hoy
elif periodo == "Mes anterior":
    desde, hasta = ini_mes_ant, fin_mes_ant
elif periodo == "Últimos 30 días":
    desde, hasta = hoy - timedelta(days=30), hoy
elif periodo == "Últimos 60 días":
    desde, hasta = hoy - timedelta(days=60), hoy
elif periodo == "Últimos 90 días":
    desde, hasta = hoy - timedelta(days=90), hoy
elif periodo == "Todo el historial":
    desde, hasta = fecha_min, fecha_max
else:
    guardado = st.session_state.get("rango_custom", (fecha_min, fecha_max))
    desde, hasta = guardado[0], guardado[1]
    # Se abre el calendario apenas se elige "Personalizado"
    if periodo_prev != "Personalizado" or st.session_state.pop("reabrir_cal", False):
        dialogo_fechas(fecha_min, fecha_max)

# ══════════════════════════════════════════
# SALDO ACUMULADO — sobre TODO el historial
# ══════════════════════════════════════════

base = mov.copy()
saldo_inicial = 0.0

if cuenta_sel != "Todas":
    base = base[base["Cuenta Nombre"] == cuenta_sel]
    ids = [k for k, v in d_cuentas.items() if v == cuenta_sel]
    if ids:
        fila = cuentas[cuentas["ID"].astype(str).str.strip() == ids[0]]
        if not fila.empty:
            saldo_inicial = float(fila["Saldo Inicial"].iloc[0])
elif proyecto_sel == "Todos":
    ctas_visibles = set(cta["Nombre Cuenta"].astype(str).str.strip())
    base = base[base["Cuenta Nombre"].isin(ctas_visibles)]
    saldo_inicial = float(
        cuentas[
            cuentas["Nombre Cuenta"].astype(str).str.strip().isin(ctas_visibles)
        ]["Saldo Inicial"].sum()
    )

if proyecto_sel != "Todos":
    base = base[base["Proyecto Nombre"] == proyecto_sel]
    if cuenta_sel == "Todas":
        saldo_inicial = 0.0

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

# ══════════════════════════════════════════
# KPIs
# ══════════════════════════════════════════

if "desc" not in st.session_state:
    st.session_state.desc = True

ingresos = df[df["Monto Neto"] > 0]["Monto Neto"].sum()
egresos = df[df["Monto Neto"] < 0]["Monto Neto"].sum()
saldo_actual = base["Saldo Cierre"].iloc[-1] if len(base) > 0 else saldo_inicial

etiqueta_saldo = (
    "Neto del proyecto"
    if (proyecto_sel != "Todos" and cuenta_sel == "Todas")
    else "Saldo actual"
)

k1, k2 = st.columns(2)
with k1:
    st.markdown(
        f'<div class="kpi"><div class="kpi-label">Ingresos / Egresos</div>'
        f'<div class="kpi-doble"><span class="pos">+{fmt(ingresos)}</span>'
        f'<span class="neg">-{fmt(abs(egresos))}</span></div></div>',
        unsafe_allow_html=True,
    )
with k2:
    clase = "pos" if saldo_actual >= 0 else "neg"
    st.markdown(
        f'<div class="kpi"><div class="kpi-label">{etiqueta_saldo}</div>'
        f'<div class="kpi-val {clase}">S/ {fmt(saldo_actual)}</div></div>',
        unsafe_allow_html=True,
    )

# ── Resumen del periodo + orden ──
if periodo == "Personalizado":
    r1, rcal, r2 = st.columns([3.6, 1.4, 1.5])
else:
    r1, r2 = st.columns([5, 1.5])
    rcal = None

with r1:
    st.markdown(
        f'<div class="fila-orden">{len(df)} movimientos · '
        f'{fecha_es(desde, False)} al {fecha_es(hasta, False)}</div>',
        unsafe_allow_html=True,
    )
if rcal is not None:
    with rcal:
        if st.button("📅 Cambiar", use_container_width=True):
            st.session_state["reabrir_cal"] = True
            st.rerun()
with r2:
    flecha = "↓" if st.session_state.desc else "↑"
    if st.button(f"{flecha} Fecha", use_container_width=True):
        st.session_state.desc = not st.session_state.desc

descendente = st.session_state.desc

df = df.sort_values(
    ["Fecha", "_RowNumber"], ascending=[not descendente, not descendente]
).reset_index(drop=True)

if len(df) == 0:
    st.info("No hay movimientos con los filtros seleccionados.")
    st.stop()

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
    extra = f" · {r['Cuenta Nombre']}" if cuenta_sel == "Todas" else ""
    html.append(
        f'<div class="mov-row">'
        f'<div class="mov-izq">'
        f'<span class="mov-desc {signo}">{r["Desc"]}</span>'
        f'<span class="mov-cat">{r["CatSub"]}{extra}</span>'
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

cols_exp = ["Fecha", "Cuenta Nombre", "Desc", "CatSub", "Proyecto Nombre",
            "Monto Neto", "Saldo Cierre"]
cols_exp = [c for c in cols_exp if c in df.columns]
exportar = df[cols_exp].copy()
exportar["Fecha"] = exportar["Fecha"].dt.strftime("%d/%m/%Y")
exportar.columns = [
    {"Cuenta Nombre": "Cuenta", "Desc": "Descripción", "CatSub": "Categoría",
     "Proyecto Nombre": "Proyecto", "Monto Neto": "Monto",
     "Saldo Cierre": "Saldo cierre"}.get(c, c)
    for c in cols_exp
]

csv = exportar.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    label="📥 Descargar movimientos (CSV)",
    data=csv,
    file_name=f"movimientos_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv",
)
