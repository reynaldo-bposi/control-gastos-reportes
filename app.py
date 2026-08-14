import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import calendar
import plotly.graph_objects as go
import conciliacion

# ══════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════

SHEET_ID = "1Wx5N3uAi-_4iLpYOibXgXisT3PizOlwDWQtAn1str_w"

st.set_page_config(
    page_title="Control de Gastos",
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

/* ── Menú principal (segmented control) a todo el ancho ── */
.st-key-nav_main [data-testid="stSegmentedControl"]{width:100%;}
.st-key-nav_main [data-testid="stSegmentedControl"] > div{width:100%;}
.st-key-nav_main [data-testid="stSegmentedControl"] button{flex:1 1 0;}

.titulo{font-size:22px;font-weight:700;line-height:1.4;padding:2px 0 10px 0;}
.sub{font-size:16px;font-weight:700;margin:20px 0 8px 0;}

.kpi{background:#f8f9fa;border-radius:10px;padding:9px 12px;text-align:center;}
.kpi-label{font-size:10px;color:#868e96;text-transform:uppercase;
  letter-spacing:.4px;margin-bottom:2px;}
.kpi-val{font-size:18px;font-weight:700;}
.kpi-doble{font-size:15px;font-weight:700;display:flex;flex-wrap:wrap;
  justify-content:center;align-items:baseline;gap:2px 10px;}
.kpi-doble span{white-space:nowrap;}
.kpi-delta{font-size:10px;margin-top:2px;}

div[data-testid="stButton"] button{height:28px;min-height:28px;border-radius:6px;
  background:#f8f9fa;border:1px solid #e9ecef;font-size:12px;
  padding:0 8px;line-height:1;}
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

.var-row{display:flex;justify-content:space-between;align-items:center;
  padding:8px 12px;background:#f8f9fa;border-radius:8px;margin-bottom:5px;
  font-size:13px;}
.var-monto{font-weight:700;}

.card{background:#fff;border:1px solid #e9ecef;border-radius:12px;
  padding:14px 16px;}
.card-tit{font-size:14px;font-weight:700;margin-bottom:8px;}
.card-val{font-size:20px;font-weight:700;margin-bottom:8px;}
.card-row{font-size:12px;display:flex;justify-content:space-between;
  padding:4px 0;border-top:1px solid #f1f3f5;}
.card-nota{font-size:11px;color:#adb5bd;margin-top:6px;}

.barra-bg{height:6px;background:#f1f3f5;border-radius:3px;overflow:hidden;}
.barra-fill{height:100%;}
.proy-lbl{display:flex;justify-content:space-between;font-size:12px;
  margin-bottom:3px;}
.proy-nota{font-size:11px;color:#adb5bd;margin-top:3px;margin-bottom:10px;}

.pos{color:#2b8a3e;}
.neg{color:#c92a2a;}
.gris{color:#868e96;}
</style>
""", unsafe_allow_html=True)

MESES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "setiembre", 10: "octubre", 11: "noviembre",
    12: "diciembre",
}
MESES_C = {k: v[:3] for k, v in MESES.items()}
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


def fmt0(v):
    return f"{v:,.0f}"


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


# ══════════════════════════════════════════
# CARGA Y PREPARACIÓN
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

mov["Tipo"] = mov["Tipo Mov."].astype(str).str.strip() if "Tipo Mov." in mov.columns else ""
mov["Periodo"] = mov["Fecha"].dt.to_period("M")

fecha_min = mov["Fecha"].min().date()
fecha_max = mov["Fecha"].max().date()
hoy = datetime.now().date()

# ══════════════════════════════════════════
# NAVEGACIÓN
# ══════════════════════════════════════════

vista = st.segmented_control(
    "Vista", ["Movimientos", "Reportes", "Conciliación"],
    label_visibility="collapsed", default="Movimientos", key="nav_main",
)
vista = vista or "Movimientos"

# ══════════════════════════════════════════
# VISTA: MOVIMIENTOS
# ══════════════════════════════════════════

if vista == "Movimientos":

    t1, t2 = st.columns([3, 1.6])
    with t1:
        st.markdown('<div class="titulo">Movimientos</div>', unsafe_allow_html=True)
    with t2:
        solo_activos = st.toggle("Solo activos", value=True)

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

    OPCIONES_PERIODO = [
        "Este mes", "Mes anterior", "Últimos 30 días", "Últimos 60 días",
        "Últimos 90 días", "Todo el historial", "Personalizado",
    ]
    periodo_prev = st.session_state.get("periodo_sel", "Todo el historial")

    f1, f2 = st.columns(2)
    with f1:
        cuenta_sel = st.selectbox(
            "Cuenta", opciones_cuenta, format_func=lambda x: etiquetas.get(x, x)
        )
    with f2:
        proyecto_sel = st.selectbox("Proyecto", opciones_proy)

    if periodo_prev == "Personalizado":
        g1, gcal, g2, g3 = st.columns([1.5, 1.8, 1.1, 1.1])
    else:
        g1, g2, g3 = st.columns([1.8, 1.3, 1.3])
        gcal = None

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
        if gcal is not None:
            with gcal:
                rango = st.date_input(
                    "Fechas", value=(desde, hasta),
                    min_value=fecha_min, max_value=fecha_max,
                    format="DD/MM/YYYY", key="cal_custom",
                )
                if isinstance(rango, tuple) and len(rango) == 2:
                    st.session_state["rango_custom"] = rango
                    desde, hasta = rango

    if periodo == "Personalizado" and periodo_prev != "Personalizado":
        components.html(
            """
            <script>
            const doc = window.parent.document;
            let n = 0;
            const t = setInterval(() => {
                n++;
                const c = doc.querySelector('[data-testid="stDateInput"] input');
                if (c) { c.focus(); c.click(); clearInterval(t); }
                if (n > 20) clearInterval(t);
            }, 100);
            </script>
            """,
            height=0,
        )

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
        visibles = set(cta["Nombre Cuenta"].astype(str).str.strip())
        base = base[base["Cuenta Nombre"].isin(visibles)]
        saldo_inicial = float(
            cuentas[
                cuentas["Nombre Cuenta"].astype(str).str.strip().isin(visibles)
            ]["Saldo Inicial"].sum()
        )

    if proyecto_sel != "Todos":
        base = base[base["Proyecto Nombre"] == proyecto_sel]
        if cuenta_sel == "Todas":
            saldo_inicial = 0.0

    base = base.sort_values(["Fecha", "_RowNumber"], ascending=[True, True])
    base["Saldo Cierre"] = saldo_inicial + base["Monto Neto"].cumsum()

    df = base[(base["Fecha"].dt.date >= desde) & (base["Fecha"].dt.date <= hasta)].copy()

    if perfil_sel != "Todos" and "Perfil" in df.columns:
        df = df[df["Perfil"].astype(str).str.strip() == perfil_sel]
    if tipo_sel != "Todos":
        df = df[df["Tipo"] == tipo_sel]

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

    r1, r2 = st.columns([5, 1.5])
    with r1:
        st.markdown(
            f'<div class="fila-orden">{len(df)} movimientos · '
            f'{fecha_es(desde, False)} al {fecha_es(hasta, False)}</div>',
            unsafe_allow_html=True,
        )
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
        "📥 Descargar movimientos (CSV)", csv,
        file_name=f"movimientos_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

# ══════════════════════════════════════════
# VISTA: REPORTES
# ══════════════════════════════════════════

elif vista == "Reportes":
    tr1, tr2 = st.columns([3, 1.6])
    with tr1:
        st.markdown('<div class="titulo">Reportes</div>', unsafe_allow_html=True)
    with tr2:
        solo_act_r = st.toggle("Solo activos", value=True, key="tg_resumen")

    # Sub-navegación de reportes
    rep_vista = st.radio(
        "Reporte", ["Gráfico circular", "Gráfico evolutivo"],
        horizontal=True, label_visibility="collapsed", key="rep_vista",
    )

    # ── Listas para filtros ──
    col_act = buscar_col(cuentas, ["Activa", "Activo"])
    col_ord = buscar_col(cuentas, ["Orden", "orden", "N° Orden"])
    col_mon = buscar_col(cuentas, ["Moneda"])

    ctar = cuentas.copy()
    if solo_act_r and col_act:
        ctar = ctar[ctar[col_act].astype(str).str.strip().str.lower().isin(ACTIVOS)]
    ctar["_ord"] = a_numero(ctar[col_ord]) if col_ord else range(len(ctar))
    ctar["_mon"] = ctar[col_mon].astype(str).str.strip().str.upper() if col_mon else "PEN"
    ctar["_pri"] = ctar["_mon"].map({"PEN": 0, "USD": 1}).fillna(9)
    ctar = ctar.sort_values(["_pri", "_mon", "_ord", "Nombre Cuenta"])

    opc_cta = ["Todas"]
    etq_cta = {"Todas": "Todas las cuentas"}
    mon_act = None
    for _, r in ctar.iterrows():
        nom = str(r["Nombre Cuenta"]).strip()
        if not nom:
            continue
        if r["_mon"] != mon_act:
            mon_act = r["_mon"]
            sp = f"── {mon_act} ──"
            opc_cta.append(sp)
            etq_cta[sp] = sp
        opc_cta.append(nom)
        etq_cta[nom] = f"   {nom}"

    opc_proy = ["Todos"]
    if not proyectos.empty:
        c_est = buscar_col(proyectos, ["Estado"])
        c_nom = buscar_col(proyectos, ["Nombre Proyecto", "Nombre"])
        pr = proyectos.copy()
        if solo_act_r and c_est:
            pr = pr[pr[c_est].astype(str).str.strip().str.lower().isin(ACTIVOS)]
        if c_nom:
            opc_proy += sorted([n for n in pr[c_nom].astype(str).str.strip().unique() if n])

    anios = sorted(mov["Fecha"].dt.year.unique(), reverse=True)

    # Meses completos recientes (dinámicos) para filtrar rápido; se saltan
    # los 2 primeros porque ya están como "Este mes" / "Mes anterior".
    fmin_mes = fecha_min.replace(day=1)
    map_meses, _y, _m, _c = {}, hoy.year, hoy.month, 0
    for _i in range(30):
        _d0 = datetime(_y, _m, 1).date()
        if _i >= 2 and _d0 >= fmin_mes and _c < 12:
            map_meses[f"{MESES[_m].capitalize()} {_y}"] = (_y, _m)
            _c += 1
        _m -= 1
        if _m == 0:
            _m, _y = 12, _y - 1

    if rep_vista == "Gráfico evolutivo":
        opc_periodo = [f"Año {a}" for a in anios] + ["Todo el historial", "Personalizado"]
        per_key = "per_evolutivo"
        _idx_def = opc_periodo.index("Todo el historial")
    else:
        opc_periodo = (["Este mes", "Mes anterior",
                        "Últimos 30 días", "Últimos 60 días", "Últimos 90 días"]
                       + list(map_meses.keys())
                       + [f"Año {a}" for a in anios]
                       + ["Todo el historial", "Personalizado"])
        per_key = "per_circular"
        _idx_def = 0

    # ── Filtros ──
    q1, q2 = st.columns(2)
    with q1:
        per_sel = st.selectbox("Periodo", opc_periodo, index=_idx_def, key=per_key)
    with q2:
        cta_r = st.selectbox("Cuenta", opc_cta,
                             format_func=lambda x: etq_cta.get(x, x), key="cta_resumen")

    if rep_vista == "Gráfico circular":
        q3, q4 = st.columns(2)
        with q3:
            proy_r = st.selectbox("Proyecto", opc_proy, key="proy_resumen")
        with q4:
            tipo_r = st.selectbox("Tipo", ["Egreso", "Ingreso"], key="tipo_resumen")
    else:
        # En el evolutivo, Proyecto y Tipo no aplican (los modos ya separan
        # ingresos/egresos y la vista es de tendencia, no puntual).
        proy_r = "Todos"
        tipo_r = "Egreso"

    if per_sel == "Personalizado":
        _g = st.session_state.get("rango_rep", (hoy - timedelta(days=30), hoy))
        _rango = st.date_input("Rango de fechas", value=_g,
                               min_value=fecha_min, max_value=fecha_max,
                               format="DD/MM/YYYY", key="cal_rep")
        if isinstance(_rango, tuple) and len(_rango) == 2:
            st.session_state["rango_rep"] = _rango

    if cta_r.startswith("──"):
        cta_r = "Todas"

    # ── Rango del periodo y su comparativo ──
    pri_mes = hoy.replace(day=1)
    fin_ant = pri_mes - timedelta(days=1)
    ini_ant = fin_ant.replace(day=1)

    def _rango_mes(y, m):
        ini = datetime(y, m, 1).date()
        fin = datetime(y, m, calendar.monthrange(y, m)[1]).date()
        if y == hoy.year and m == hoy.month:
            fin = hoy
        return ini, fin

    es_mes_curso = False
    if per_sel == "Este mes":
        d_ini, d_fin = pri_mes, hoy
        a_ini, a_fin = ini_ant, fin_ant
        lbl_ant = MESES_C[ini_ant.month]
        gran_def = "Mensual"
        es_mes_curso = True
    elif per_sel == "Mes anterior":
        d_ini, d_fin = ini_ant, fin_ant
        prev_fin = ini_ant - timedelta(days=1)
        a_ini, a_fin = prev_fin.replace(day=1), prev_fin
        lbl_ant = MESES_C[a_ini.month]
        gran_def = "Mensual"
    elif per_sel in ("Últimos 30 días", "Últimos 60 días", "Últimos 90 días"):
        ndias = int(per_sel.split()[1])
        d_ini, d_fin = hoy - timedelta(days=ndias), hoy
        a_fin = d_ini - timedelta(days=1)
        a_ini = a_fin - timedelta(days=ndias)
        lbl_ant = f"{ndias}d previos"
        gran_def = "Mensual"
    elif per_sel in map_meses:
        y, m = map_meses[per_sel]
        d_ini, d_fin = _rango_mes(y, m)
        pm = datetime(y, m, 1).date() - timedelta(days=1)
        a_ini, a_fin = pm.replace(day=1), pm
        lbl_ant = MESES_C[pm.month]
        gran_def = "Mensual"
        es_mes_curso = (y == hoy.year and m == hoy.month)
    elif per_sel.startswith("Año"):
        anio = int(per_sel.split()[1])
        d_ini, d_fin = datetime(anio, 1, 1).date(), datetime(anio, 12, 31).date()
        a_ini, a_fin = datetime(anio - 1, 1, 1).date(), datetime(anio - 1, 12, 31).date()
        lbl_ant = str(anio - 1)
        gran_def = "Mensual"
    elif per_sel == "Personalizado":
        g = st.session_state.get("rango_rep", (hoy - timedelta(days=30), hoy))
        d_ini, d_fin = g[0], g[1]
        a_ini, a_fin = None, None
        lbl_ant = ""
        gran_def = "Anual" if (d_fin - d_ini).days > 366 else "Mensual"
    else:  # Todo el historial
        d_ini, d_fin = fecha_min, fecha_max
        a_ini, a_fin = None, None
        lbl_ant = ""
        gran_def = "Anual"

    # ── Base filtrada ──
    dfr = mov.copy()
    if cta_r != "Todas":
        dfr = dfr[dfr["Cuenta Nombre"] == cta_r]
    elif solo_act_r:
        vis = set(ctar["Nombre Cuenta"].astype(str).str.strip())
        dfr = dfr[dfr["Cuenta Nombre"].isin(vis)]
    if proy_r != "Todos":
        dfr = dfr[dfr["Proyecto Nombre"] == proy_r]

    real = dfr[dfr["Tipo"] != "Transferencia"]

    act = real[(real["Fecha"].dt.date >= d_ini) & (real["Fecha"].dt.date <= d_fin)]
    if a_ini:
        ant = real[(real["Fecha"].dt.date >= a_ini) & (real["Fecha"].dt.date <= a_fin)]
    else:
        ant = real.iloc[0:0]

    ing = act[act["Monto Neto"] > 0]["Monto Neto"].sum()
    egr = abs(act[act["Monto Neto"] < 0]["Monto Neto"].sum())
    ing_a = ant[ant["Monto Neto"] > 0]["Monto Neto"].sum()
    egr_a = abs(ant[ant["Monto Neto"] < 0]["Monto Neto"].sum())
    ahorro = ing - egr
    pct_ahorro = (ahorro / ing * 100) if ing > 0 else 0

    def delta(actual, anterior, invertir=False):
        if anterior == 0 or not lbl_ant:
            return '<div class="kpi-delta gris">sin comparativo</div>'
        p = (actual - anterior) / anterior * 100
        sube = p >= 0
        bueno = (not sube) if invertir else sube
        clase = "pos" if bueno else "neg"
        fl = "▲" if sube else "▼"
        return (f'<div class="kpi-delta {clase}">{fl} {abs(p):.0f}% '
                f'vs {lbl_ant}</div>')

    # ── Total del tipo seleccionado (para KPIs del circular) ──
    tot_tipo = egr if tipo_r == "Egreso" else ing
    tot_tipo_ant = egr_a if tipo_r == "Egreso" else ing_a

    # ── Filtro de categoría: un solo desplegable compacto, arriba de los KPIs ──
    cat_activa = None
    if rep_vista == "Gráfico circular":
        _sig_c = (act["Monto Neto"] < 0) if tipo_r == "Egreso" else (act["Monto Neto"] > 0)
        _bc = act[_sig_c].copy()
        _bc["_abs"] = _bc["Monto Neto"].abs()
        _catord = _bc.groupby("Cat Nombre")["_abs"].sum().sort_values(ascending=False)
        cat_opts = ["Todas"] + [c for c in _catord.index
                                if str(c).strip() and str(c) != "nan"]
        if st.session_state.get("cat_filtro") not in cat_opts:
            st.session_state["cat_filtro"] = "Todas"
        _csel = st.selectbox("Filtrar por categoría", cat_opts, key="cat_filtro")
        cat_activa = None if _csel == "Todas" else _csel

    sub_cat = sub_cat_ant = None
    if cat_activa:
        _sig = (act["Monto Neto"] < 0) if tipo_r == "Egreso" else (act["Monto Neto"] > 0)
        sub_cat = act[(act["Cat Nombre"] == cat_activa) & _sig]
        if sub_cat.empty:
            cat_activa = None
        else:
            _siga = (ant["Monto Neto"] < 0) if tipo_r == "Egreso" else (ant["Monto Neto"] > 0)
            sub_cat_ant = ant[(ant["Cat Nombre"] == cat_activa) & _siga]

    if rep_vista == "Gráfico evolutivo":
        # Resumen del periodo, sin depender del Tipo (los modos ya lo separan)
        n_mov = len(act)
        cls_ah = "pos" if ahorro >= 0 else "neg"
        k1, k2 = st.columns(2)
        with k1:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">Ingresos</div>'
                f'<div class="kpi-val pos">S/ {fmt0(ing)}</div>'
                f'{delta(ing, ing_a)}</div>', unsafe_allow_html=True)
        with k2:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">Egresos</div>'
                f'<div class="kpi-val neg">S/ {fmt0(egr)}</div>'
                f'{delta(egr, egr_a, invertir=True)}</div>', unsafe_allow_html=True)
        k3, k4 = st.columns(2)
        with k3:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">Neto</div>'
                f'<div class="kpi-val {cls_ah}">S/ {fmt0(ahorro)}</div>'
                f'<div class="kpi-delta gris">{pct_ahorro:.0f}% de lo que entró</div></div>',
                unsafe_allow_html=True)
        with k4:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">Movimientos</div>'
                f'<div class="kpi-val">{n_mov}</div>'
                f'<div class="kpi-delta gris">en el periodo</div></div>',
                unsafe_allow_html=True)
    elif cat_activa:
        # KPIs de la categoría seleccionada
        tot_cat = abs(sub_cat["Monto Neto"].sum())
        tot_cat_ant = abs(sub_cat_ant["Monto Neto"].sum()) if sub_cat_ant is not None else 0
        pct_cat = (tot_cat / tot_tipo * 100) if tot_tipo else 0
        n_cat = len(sub_cat)
        ticket = tot_cat / n_cat if n_cat else 0
        et_tipo = "los egresos" if tipo_r == "Egreso" else "los ingresos"
        lab_g = "Gasto" if tipo_r == "Egreso" else "Ingreso"
        cls_c = "neg" if tipo_r == "Egreso" else "pos"

        k1, k2 = st.columns(2)
        with k1:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">{lab_g} en {cat_activa}</div>'
                f'<div class="kpi-val {cls_c}">S/ {fmt0(tot_cat)}</div>'
                f'{delta(tot_cat, tot_cat_ant, invertir=(tipo_r == "Egreso"))}</div>',
                unsafe_allow_html=True)
        with k2:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">% del total</div>'
                f'<div class="kpi-val">{pct_cat:.0f}%</div>'
                f'<div class="kpi-delta gris">de {et_tipo} del periodo</div></div>',
                unsafe_allow_html=True)
        k3, k4 = st.columns(2)
        with k3:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">Movimientos</div>'
                f'<div class="kpi-val">{n_cat}</div>'
                f'<div class="kpi-delta gris">en el periodo</div></div>',
                unsafe_allow_html=True)
        with k4:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">Ticket promedio</div>'
                f'<div class="kpi-val">S/ {fmt0(ticket)}</div>'
                f'<div class="kpi-delta gris">por movimiento</div></div>',
                unsafe_allow_html=True)
    else:
        # KPIs del tipo seleccionado (sin proyección)
        et = "Egresos" if tipo_r == "Egreso" else "Ingresos"
        cls_t = "neg" if tipo_r == "Egreso" else "pos"
        _sig_t = (act["Monto Neto"] < 0) if tipo_r == "Egreso" else (act["Monto Neto"] > 0)
        n_tipo = int(_sig_t.sum())
        ticket_t = tot_tipo / n_tipo if n_tipo else 0

        k1, k2, k3 = st.columns(3)
        with k1:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">{et}</div>'
                f'<div class="kpi-val {cls_t}">S/ {fmt0(tot_tipo)}</div>'
                f'{delta(tot_tipo, tot_tipo_ant, invertir=(tipo_r == "Egreso"))}</div>',
                unsafe_allow_html=True)
        with k2:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">Movimientos</div>'
                f'<div class="kpi-val">{n_tipo}</div>'
                f'<div class="kpi-delta gris">en el periodo</div></div>',
                unsafe_allow_html=True)
        with k3:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">Ticket prom.</div>'
                f'<div class="kpi-val">S/ {fmt0(ticket_t)}</div>'
                f'<div class="kpi-delta gris">por movimiento</div></div>',
                unsafe_allow_html=True)

    if rep_vista == "Gráfico evolutivo":
        # ══════════════════════════════════════
        # EVOLUTIVO
        # ══════════════════════════════════════

        modo_evo = st.segmented_control(
            "Modo", ["Ingresos vs egresos", "Egresos por categoría",
                     "Ingresos por categoría"],
            default="Ingresos vs egresos", key="modo_evo",
            label_visibility="collapsed")
        modo_evo = modo_evo or "Ingresos vs egresos"

        # Categoría (solo en modos por categoría) + granularidad
        cat_evo = "Todas"
        if modo_evo == "Ingresos vs egresos":
            gcol = st.columns([3, 1.4])[1]
            with gcol:
                gran = st.selectbox("Ver por", ["Mensual", "Anual"],
                                    index=0 if gran_def == "Mensual" else 1,
                                    key="gran_evo", label_visibility="collapsed")
        else:
            _sig_e = (real["Monto Neto"] < 0) if modo_evo.startswith("Egresos") \
                else (real["Monto Neto"] > 0)
            _cats = real[_sig_e].groupby("Cat Nombre")["Monto Neto"].sum().abs()
            _cats = _cats[_cats > 0].sort_values(ascending=False)
            ce1, ce2 = st.columns([3, 1.4])
            with ce1:
                cat_evo = st.selectbox("Categoría", ["Todas"] + list(_cats.index),
                                       key="cat_evo", label_visibility="collapsed")
            with ce2:
                gran = st.selectbox("Ver por", ["Mensual", "Anual"],
                                    index=0 if gran_def == "Mensual" else 1,
                                    key="gran_evo", label_visibility="collapsed")

        # Cubos de tiempo (claves + etiquetas)
        if gran == "Mensual":
            if per_sel.startswith("Año"):
                anio = int(per_sel.split()[1])
                claves = [pd.Period(f"{anio}-{m:02d}", freq="M") for m in range(1, 13)]
            elif per_sel == "Todo el historial":
                claves = sorted(real["Periodo"].unique())[-24:]
            else:
                fin_p = pd.Period(d_fin, freq="M")
                claves = [fin_p - i for i in range(11, -1, -1)]
            etq = [f"{MESES_C[p.month]} {str(p.year)[2:]}" for p in claves]
            col_bucket = real["Periodo"]
        else:
            claves = sorted(real["Fecha"].dt.year.unique())
            etq = [str(a) for a in claves]
            col_bucket = real["Fecha"].dt.year

        COLS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
                "#008300", "#4a3aa7", "#e34948"]

        if modo_evo == "Ingresos vs egresos":
            st.markdown('<div class="sub">Ingresos vs egresos</div>',
                        unsafe_allow_html=True)
            vi, ve, va = [], [], []
            for k in claves:
                d = real[col_bucket == k]
                i_ = d[d["Monto Neto"] > 0]["Monto Neto"].sum()
                e_ = abs(d[d["Monto Neto"] < 0]["Monto Neto"].sum())
                vi.append(i_)
                ve.append(e_)
                va.append(i_ - e_)
            fig = go.Figure()
            fig.add_bar(x=etq, y=vi, name="Ingresos", marker_color="#1baf7a")
            fig.add_bar(x=etq, y=ve, name="Egresos", marker_color="#eb6834")
            fig.add_scatter(x=etq, y=va, name="Neto", mode="lines+markers",
                            line=dict(color="#2a78d6", width=2), marker=dict(size=6))
            fig.update_layout(barmode="group")
        else:
            _sig_e = (real["Monto Neto"] < 0) if modo_evo.startswith("Egresos") \
                else (real["Monto Neto"] > 0)
            base = real[_sig_e].copy()
            if cat_evo != "Todas":
                base = base[base["Cat Nombre"] == cat_evo]
                dim_col = "Sub Nombre"
                titulo = f"{cat_evo} · subcategorías en el tiempo"
            else:
                dim_col = "Cat Nombre"
                titulo = f"{modo_evo} en el tiempo"
            st.markdown(f'<div class="sub">{titulo}</div>', unsafe_allow_html=True)

            base["_k"] = base[dim_col].apply(
                lambda s: s if (str(s).strip() and str(s) != "nan") else "(sin dato)")
            base["_b"] = base["Periodo"] if gran == "Mensual" else base["Fecha"].dt.year
            tot_by = base.groupby("_k")["Monto Neto"].sum().abs().sort_values(ascending=False)
            top_series = list(tot_by.index[:6])
            otros_series = list(tot_by.index[6:])

            fig = go.Figure()
            if not top_series:
                st.info("No hay datos para este modo en el periodo.")
            for i, s in enumerate(top_series):
                serie = base[base["_k"] == s].groupby("_b")["Monto Neto"].sum().abs()
                ys = [float(serie.get(k, 0)) for k in claves]
                fig.add_bar(x=etq, y=ys, name=str(s)[:18],
                            marker_color=COLS[i % len(COLS)])
            if otros_series:
                s_o = base[base["_k"].isin(otros_series)].groupby("_b")["Monto Neto"].sum().abs()
                ys_o = [float(s_o.get(k, 0)) for k in claves]
                fig.add_bar(x=etq, y=ys_o, name="Otros", marker_color="#b9bec4")
            # apiladas = composición por periodo
            fig.update_layout(barmode="stack")

        fig.update_layout(
            height=300, margin=dict(l=0, r=0, t=8, b=64),
            legend=dict(orientation="h", yanchor="top", y=-0.22, x=0,
                        font=dict(size=11)),
            hovermode="x unified", yaxis_title="", xaxis_title="",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

    if rep_vista == "Gráfico circular":
        # ══════════════════════════════════════
        # PIE POR CATEGORÍA
        # ══════════════════════════════════════

        if tipo_r == "Egreso":
            sel = act[act["Monto Neto"] < 0].copy()
            sel_ant = ant[ant["Monto Neto"] < 0].copy()
            base_lbl = "Egresos"
        else:
            sel = act[act["Monto Neto"] > 0].copy()
            sel_ant = ant[ant["Monto Neto"] > 0].copy()
            base_lbl = "Ingresos"

        # Composición por categoría (se conserva para el % del total en el detalle)
        por_cat = sel.groupby("Cat Nombre")["Monto Neto"].sum().abs()
        por_cat = por_cat[por_cat > 0].sort_values(ascending=False)

        # Dimensión de la torta: por categoría (Todas) o por subcategoría (al filtrar)
        if cat_activa:
            dim_col = "Sub Nombre"
            base_pie = sel[sel["Cat Nombre"] == cat_activa].copy()
            base_pie_ant = sel_ant[sel_ant["Cat Nombre"] == cat_activa].copy()
            titulo_pie = f"{cat_activa} · por subcategoría"
            var_titulo = f"Subcategorías vs {lbl_ant}"
        else:
            dim_col = "Cat Nombre"
            base_pie = sel
            base_pie_ant = sel_ant
            titulo_pie = f"{base_lbl} por categoría"
            var_titulo = f"Variación vs {lbl_ant}"

        st.markdown(f'<div class="sub">{titulo_pie}</div>', unsafe_allow_html=True)

        if len(base_pie) == 0:
            st.info("No hay movimientos de este tipo en el periodo seleccionado.")
        else:
            def _agg(df):
                g = df.copy()
                g["_k"] = g[dim_col].apply(
                    lambda s: s if (str(s).strip() and str(s) != "nan") else "(sin dato)")
                r = g.groupby("_k")["Monto Neto"].sum().abs()
                return r[r > 0].sort_values(ascending=False)

            por_pie = _agg(base_pie)

            COLORES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
                       "#008300", "#4a3aa7", "#e34948", "#888780"]

            if len(por_pie) > 9:
                top = por_pie.head(8)
                otros = por_pie.iloc[8:].sum()
                etiquetas_pie = list(top.index) + ["Otros"]
                valores_pie = list(top.values) + [otros]
            else:
                etiquetas_pie = list(por_pie.index)
                valores_pie = list(por_pie.values)

            figp = go.Figure(go.Pie(
                labels=etiquetas_pie, values=valores_pie, hole=0.45,
                marker=dict(colors=COLORES[:len(etiquetas_pie)],
                            line=dict(color="#ffffff", width=2)),
                textinfo="percent", textposition="inside",
                hovertemplate="%{label}<br>S/ %{value:,.2f} (%{percent})<extra></extra>",
                sort=True,
            ))
            figp.update_layout(
                height=340, margin=dict(l=0, r=0, t=6, b=0),
                legend=dict(orientation="v", x=1, y=0.5, font=dict(size=11)),
                annotations=[dict(
                    text=f"S/ {fmt0(por_pie.sum())}", x=0.5, y=0.5,
                    font=dict(size=15), showarrow=False,
                )],
            )
            st.plotly_chart(figp, use_container_width=True)
            cap_pie = ("Composición de la categoría filtrada." if cat_activa
                       else "La torta es referencial; para filtrar usa el desplegable de arriba.")
            st.caption(cap_pie)

            # ── Variación vs periodo anterior (misma dimensión que la torta) ──
            if len(base_pie_ant) > 0 and lbl_ant:
                a_ = por_pie
                b_ = _agg(base_pie_ant)
                var = a_.subtract(b_, fill_value=0).sort_values(ascending=False)
                var = var[var.abs() > 0.5].head(8)
                if len(var) > 0:
                    st.markdown(f'<div class="sub">{var_titulo}</div>',
                                unsafe_allow_html=True)
                    filas = []
                    for c, v in var.items():
                        malo = (v > 0) if tipo_r == "Egreso" else (v < 0)
                        cl = "neg" if malo else "pos"
                        sg = "+" if v > 0 else "−"
                        filas.append(
                            f'<div class="var-row"><span>{c}</span>'
                            f'<span class="var-monto {cl}">{sg}S/ {fmt0(abs(v))}</span></div>')
                    st.markdown("".join(filas), unsafe_allow_html=True)

            # ══════════════════════════════════
            # DETALLE POR CATEGORÍA
            # ══════════════════════════════════

            st.markdown('<div class="sub">Ver detalle</div>', unsafe_allow_html=True)

            if not cat_activa:
                st.caption("Elige una categoría en el filtro de arriba para ver su detalle.")
            else:
                dim = st.radio(
                    "Ver por", ["Subcategoría", "Beneficiario", "Movimientos"],
                    horizontal=True, label_visibility="collapsed", key="dim_detalle",
                )
                cat_det = cat_activa
                det = sel[sel["Cat Nombre"] == cat_det].copy()
                total_det = abs(det["Monto Neto"].sum())
                pct_det = total_det / por_cat.sum() * 100 if por_cat.sum() else 0

                st.markdown(
                    f'<div class="fila-orden"><b>{cat_det}</b> · {len(det)} movimientos · '
                    f'S/ {fmt0(total_det)} · {pct_det:.1f}% del total</div>',
                    unsafe_allow_html=True)
                if dim in ("Subcategoría", "Beneficiario"):
                    campo = "Sub Nombre" if dim == "Subcategoría" else "Desc"
                    gr = det.groupby(campo)["Monto Neto"].sum().abs()
                    gr = gr[gr > 0].sort_values(ascending=True).tail(10)
                    gr.index = [
                        (s if s and str(s) != "nan" else "(sin dato)") for s in gr.index
                    ]

                    if len(gr) > 0:
                        figd = go.Figure(go.Bar(
                            x=gr.values, y=gr.index, orientation="h",
                            marker_color="#2a78d6",
                            hovertemplate="S/ %{x:,.2f}<extra></extra>",
                        ))
                        figd.update_layout(
                            height=max(180, 32 * len(gr)),
                            margin=dict(l=0, r=0, t=6, b=0),
                            xaxis_title="", yaxis_title="",
                        )
                        st.plotly_chart(figd, use_container_width=True)
                else:
                    movs = det.sort_values("Fecha", ascending=False).head(15)
                    html = []
                    for _, r in movs.iterrows():
                        sg = "pos" if r["Monto Neto"] >= 0 else "neg"
                        mt = f"{'+' if r['Monto Neto'] >= 0 else '-'}S/ {fmt(abs(r['Monto Neto']))}"
                        sb = r["Sub Nombre"] if str(r["Sub Nombre"]) not in ("nan", "") else ""
                        pie_txt = f'{r["Fecha"].strftime("%d/%m/%Y")} · {r["Cuenta Nombre"]}'
                        if sb:
                            pie_txt += f' · {sb}'
                        html.append(
                            f'<div class="mov-row"><div class="mov-izq">'
                            f'<span class="mov-desc">{r["Desc"]}</span>'
                            f'<span class="mov-cat">{pie_txt}</span></div>'
                            f'<div class="mov-der"><span class="mov-monto {sg}">{mt}</span>'
                            f'</div></div>')
                    st.markdown("".join(html), unsafe_allow_html=True)

                    if len(det) > 15:
                        st.caption(f"Mostrando 15 de {len(det)} movimientos")

    # ══════════════════════════════════════
    # PENDIENTES Y PROYECTOS (solo en el reporte circular)
    # ══════════════════════════════════════

    if rep_vista == "Gráfico circular":
        p1, p2 = st.columns(2)

        with p1:
            if "Estado" in dfr.columns:
                pend = dfr[dfr["Estado"].astype(str).str.strip() == "Pendiente regularizar"]
            else:
                pend = dfr.iloc[0:0]
            total_p = abs(pend["Monto Neto"].sum()) if len(pend) > 0 else 0
            filas = []
            for _, r in pend.sort_values("Fecha", ascending=False).head(4).iterrows():
                filas.append(
                    f'<div class="card-row"><span class="gris">{str(r["Desc"])[:22]}</span>'
                    f'<span>S/ {fmt0(abs(r["Monto Neto"]))}</span></div>')
            if len(pend) > 0:
                dias = (hoy - pend["Fecha"].min().date()).days
                nota = f'{len(pend)} gastos · el más antiguo hace {dias} días'
            else:
                nota = "No hay gastos pendientes"
            st.markdown(
                f'<div class="card"><div class="card-tit">⚠️ Pendiente de regularizar</div>'
                f'<div class="card-val neg">S/ {fmt0(total_p)}</div>'
                f'{"".join(filas)}<div class="card-nota">{nota}</div></div>',
                unsafe_allow_html=True)

        with p2:
            bloques = []
            if not proyectos.empty:
                c_est = buscar_col(proyectos, ["Estado"])
                c_nom = buscar_col(proyectos, ["Nombre Proyecto", "Nombre"])
                c_pre = buscar_col(proyectos, ["Presupuesto PEN", "Presupuesto"])
                pr = proyectos.copy()
                if c_est and solo_act_r:
                    pr = pr[pr[c_est].astype(str).str.strip().str.lower().isin(ACTIVOS)]
                if c_nom:
                    if c_pre:
                        pr[c_pre] = a_numero(pr[c_pre])
                    for _, r in pr.head(4).iterrows():
                        nom = str(r[c_nom]).strip()
                        pres = float(r[c_pre]) if c_pre else 0.0
                        gasto = abs(mov[(mov["Proyecto Nombre"] == nom) &
                                        (mov["Monto Neto"] < 0)]["Monto Neto"].sum())
                        if pres > 0:
                            pct = gasto / pres * 100
                            color = "#1baf7a" if pct < 70 else ("#eda100" if pct < 90 else "#d03b3b")
                            bloques.append(
                                f'<div class="proy-lbl"><span>{nom[:22]}</span>'
                                f'<span class="gris">{pct:.0f}%</span></div>'
                                f'<div class="barra-bg"><div class="barra-fill" '
                                f'style="width:{min(pct, 100)}%;background:{color};"></div></div>'
                                f'<div class="proy-nota">Gastado S/ {fmt0(gasto)} '
                                f'de S/ {fmt0(pres)} de presupuesto</div>')
                        else:
                            bloques.append(
                                f'<div class="proy-lbl"><span>{nom[:22]}</span>'
                                f'<span class="gris">sin ppto.</span></div>'
                                f'<div class="proy-nota">Gastado S/ {fmt0(gasto)} · '
                                f'sin presupuesto cargado</div>')
            if not bloques:
                bloques = ['<div class="card-nota">No hay proyectos activos</div>']
            st.markdown(
                f'<div class="card"><div class="card-tit">📁 Proyectos activos</div>'
                f'<div class="card-nota" style="margin:-2px 0 8px">'
                f'Gasto acumulado vs presupuesto</div>'
                f'{"".join(bloques)}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════
# VISTA: CONCILIACIÓN
# ══════════════════════════════════════════

if vista == "Conciliación":
    conciliacion.render(mov, cuentas, conectar_sheets, SHEET_ID)
