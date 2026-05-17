import requests
import os
from datetime import datetime

# ─── TUS CLAVES ──────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ODDS_API_KEY = os.environ["ODDS_API_KEY"]
RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]

# ─── LIGAS A ANALIZAR ────────────────────────────────────────────
LIGAS = [
    "soccer_england_championship",
    "soccer_germany_bundesliga2",
    "soccer_italy_serie_b",
    "soccer_france_ligue_2",
    "soccer_spain_segunda_division",
    "soccer_netherlands_eredivisie",
    "soccer_belgium_first_div",
    "soccer_england_womens_super_league",
    "soccer_germany_frauen_bundesliga",
    "soccer_france_womens_d1",
    "soccer_spain_womens_primera",
    "soccer_italy_womens_serie_a",
    "soccer_usa_nwsl",
]

UMBRAL_EV = 0.05       # 5% → pick con valor real
UMBRAL_EV_MINIMO = -0.10  # -10% → por debajo de esto ni se menciona

# ─── FUNCIONES ───────────────────────────────────────────────────

def obtener_cuotas():
    partidos = []
    mercados = "h2h,totals,corners"
    for liga in LIGAS:
        url = f"https://api.the-odds-api.com/v4/sports/{liga}/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "eu",
            "markets": mercados,
            "bookmakers": "bet365",
            "dateFormat": "iso",
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                datos = r.json()
                for p in datos:
                    p["liga_key"] = liga
                partidos.extend(datos)
        except Exception:
            continue
    return partidos

def nombre_liga(key):
    nombres = {
        "soccer_england_championship": "Championship 🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "soccer_germany_bundesliga2": "Bundesliga 2 🇩🇪",
        "soccer_italy_serie_b": "Serie B 🇮🇹",
        "soccer_france_ligue_2": "Ligue 2 🇫🇷",
        "soccer_spain_segunda_division": "Segunda División 🇪🇸",
        "soccer_netherlands_eredivisie": "Eredivisie 🇳🇱",
        "soccer_belgium_first_div": "Belgian Pro League 🇧🇪",
        "soccer_england_womens_super_league": "WSL Femenina 🏴󠁧󠁢󠁥󠁮󠁧󠁿♀️",
        "soccer_germany_frauen_bundesliga": "Bundesliga Femenina 🇩🇪♀️",
        "soccer_france_womens_d1": "D1 Femenina 🇫🇷♀️",
        "soccer_spain_womens_primera": "Primera Femenina 🇪🇸♀️",
        "soccer_italy_womens_serie_a": "Serie A Femenina 🇮🇹♀️",
        "soccer_usa_nwsl": "NWSL Femenina 🇺🇸♀️",
    }
    return nombres.get(key, key)

def calcular_ev(prob_real, cuota):
    return (prob_real * cuota) - 1

def estimar_probabilidades(local, visitante):
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }

    def puntos_recientes(nombre_equipo):
        try:
            params = {"team": nombre_equipo, "last": 5}
            r = requests.get(url, headers=headers, params=params, timeout=10)
            if r.status_code != 200:
                return 7
            partidos = r.json().get("response", [])
            puntos = 0
            for p in partidos:
                equipos = p.get("teams", {})
                local_info = equipos.get("home", {})
                visit_info = equipos.get("away", {})
                if local_info.get("name") == nombre_equipo:
                    if local_info.get("winner"): puntos += 3
                    elif not visit_info.get("winner"): puntos += 1
                else:
                    if visit_info.get("winner"): puntos += 3
                    elif not local_info.get("winner"): puntos += 1
            return puntos
        except Exception:
            return 7

    def goles_recientes(nombre_equipo):
        try:
            params = {"team": nombre_equipo, "last": 5}
            r = requests.get(url, headers=headers, params=params, timeout=10)
            if r.status_code != 200:
                return 1.3
            partidos = r.json().get("response", [])
            total_goles = 0
            for p in partidos:
                goals = p.get("goals", {})
                total_goles += (goals.get("home") or 0) + (goals.get("away") or 0)
            return total_goles / max(len(partidos), 1)
        except Exception:
            return 1.3

    pts_local = puntos_recientes(local)
    pts_visitante = puntos_recientes(visitante)
    total = pts_local + pts_visitante + 0.001

    prob_local = min((pts_local / total) * 0.85 + 0.08, 0.75)
    prob_visitante = min((pts_visitante / total) * 0.85, 0.65)
    prob_empate = max(1 - prob_local - prob_visitante, 0.08)
    suma = prob_local + prob_empate + prob_visitante

    goles_local = goles_recientes(local)
    goles_visitante = goles_recientes(visitante)
    promedio_goles = (goles_local + goles_visitante) / 2

    prob_over25 = min(max((promedio_goles - 1.5) / 2, 0.25), 0.80)
    prob_under25 = 1 - prob_over25

    return {
        "local": round(prob_local / suma, 3),
        "empate": round(prob_empate / suma, 3),
        "visitante": round(prob_visitante / suma, 3),
        "over25": round(prob_over25, 3),
        "under25": round(prob_under25, 3),
        "over95_corners": 0.52,
        "under95_corners": 0.48,
    }

def analizar_partidos(partidos):
    picks_con_valor = []
    picks_sin_valor = []  # los mejores aunque no tengan valor
    sin_valor_nombres = []

    for partido in partidos[:25]:
        try:
            local = partido["home_team"]
            visitante = partido["away_team"]
            liga = partido.get("liga_key", "")

            bet365 = next(
                (b for b in partido.get("bookmakers", []) if b["key"] == "bet365"),
                None
            )
            if not bet365:
                continue

            probs = estimar_probabilidades(local, visitante)
            hay_valor = False
            mejor_ev_partido = -999
            mejor_pick_partido = None

            for mercado in bet365["markets"]:
                tipo = mercado["key"]
                outcomes = mercado["outcomes"]
                opciones = []

                if tipo == "h2h":
                    cuotas = {o["name"]: o["price"] for o in outcomes}
                    cuota_local = cuotas.get(local, 0)
                    cuota_empate = cuotas.get("Draw", 0)
                    cuota_visitante = cuotas.get(visitante, 0)
                    if all([cuota_local, cuota_empate, cuota_visitante]):
                        opciones = [
                            ("🏠 Gana " + local, cuota_local, probs["local"], "Resultado"),
                            ("🤝 Empate", cuota_empate, probs["empate"], "Resultado"),
                            ("✈️ Gana " + visitante, cuota_visitante, probs["visitante"], "Resultado"),
                        ]

                elif tipo == "totals":
                    for o in outcomes:
                        if o.get("point", 0) == 2.5:
                            if o["name"] == "Over":
                                opciones.append(("⚽ Más de 2.5 goles", o["price"], probs["over25"], "Goles"))
                            elif o["name"] == "Under":
                                opciones.append(("⚽ Menos de 2.5 goles", o["price"], probs["under25"], "Goles"))

                elif tipo == "corners":
                    for o in outcomes:
                        if o.get("point", 0) == 9.5:
                            if o["name"] == "Over":
                                opciones.append(("🚩 Más de 9.5 córners", o["price"], probs["over95_corners"], "Córners"))
                            elif o["name"] == "Under":
                                opciones.append(("🚩 Menos de 9.5 córners", o["price"], probs["under95_corners"], "Córners"))

                for nombre, cuota, prob, categoria in opciones:
                    ev = calcular_ev(prob, cuota)
                    pick = {
                        "partido": f"{local} vs {visitante}",
                        "liga": nombre_liga(liga),
                        "mercado": nombre,
                        "categoria": categoria,
                        "cuota": cuota,
                        "prob_real": round(prob * 100, 1),
                        "ev": round(ev * 100, 1),
                    }
                    if ev >= UMBRAL_EV:
                        picks_con_valor.append(pick)
                        hay_valor = True
                    elif ev > mejor_ev_partido and ev >= UMBRAL_EV_MINIMO:
                        mejor_ev_partido = ev
                        mejor_pick_partido = pick

            if not hay_valor:
                sin_valor_nombres.append(f"{local} vs {visitante}")
                if mejor_pick_partido:
                    picks_sin_valor.append(mejor_pick_partido)

        except Exception:
            continue

    picks_con_valor.sort(key=lambda x: x["ev"], reverse=True)
    picks_sin_valor.sort(key=lambda x: x["ev"], reverse=True)
    return picks_con_valor[:5], picks_sin_valor[:3], sin_valor_nombres

def explicar_pick(pick, es_el_mejor=False, es_sin_valor=False):
    ev = pick["ev"]

    if es_sin_valor:
        if ev >= 0:
            nivel = "⚠️ SIN VALOR CLARO"
            explicacion = "La cuota es aproximadamente justa pero no hay ventaja real. Apuesta con precaución y cantidad pequeña."
        else:
            nivel = "⚠️ VALOR NEGATIVO"
            explicacion = f"Bet365 paga menos de lo que debería ({abs(ev)}% menos). No es ideal pero es la mejor opción disponible hoy si quieres apostar."
    elif ev >= 20:
        nivel = "🔥 VALOR MUY ALTO"
        explicacion = f"Por cada 10€ apostados, matemáticamente deberías ganar {round(ev/10, 1)}€ a largo plazo."
    elif ev >= 10:
        nivel = "✅ VALOR ALTO"
        explicacion = "La cuota paga bastante más de lo que debería. Hay margen claro de beneficio."
    else:
        nivel = "👍 VALOR MODERADO"
        explicacion = "La cuota es algo mejor de lo justo. Vale la pena pero sin exagerar la apuesta."

    estrella = "⭐ MEJOR APUESTA DEL DÍA\n" if es_el_mejor else ""

    return (
        f"{estrella}"
        f"*{pick['partido']}*\n"
        f"🏆 Liga: {pick['liga']}\n"
        f"📌 Mercado: {pick['mercado']}\n"
        f"💰 Cuota Bet365: {pick['cuota']}\n"
        f"📊 Probabilidad real estimada: {pick['prob_real']}%\n"
        f"📈 Nivel: {nivel} ({'+' if ev >= 0 else ''}{ev}%)\n"
        f"💡 En cristiano: {explicacion}\n"
    )

def construir_mensaje(picks, picks_sin_valor, sin_valor_nombres):
    hoy = datetime.now().strftime("%A %d de %B de %Y").upper()
    total = len(picks) + len(sin_valor_nombres)
    lineas = [
        f"🎯 *ANÁLISIS DE APUESTAS*",
        f"📅 {hoy}\n",
    ]

    # ── PICKS CON VALOR REAL ──
    if picks:
        lineas.append(f"✅ *{len(picks)} PICKS CON VALOR REAL HOY:*\n")
        for i, pick in enumerate(picks):
            lineas.append(explicar_pick(pick, es_el_mejor=(i == 0)))

        mejor = picks[0]
        lineas.append("─" * 30)
        lineas.append(
            f"⭐ *LA APUESTA MÁS RECOMENDABLE HOY:*\n"
            f"Partido: *{mejor['partido']}*\n"
            f"Qué hacer: Apostar a *{mejor['mercado']}*\n"
            f"Cuota: *{mejor['cuota']}* en Bet365\n"
            f"Por qué: De todos los partidos analizados hoy "
            f"este tiene el mayor desfase entre lo que paga Bet365 "
            f"y lo que realmente merece. "
            f"Valor esperado de +{mejor['ev']}% → Bet365 está pagando "
            f"más de lo que debería. Eso es exactamente lo que buscamos.\n"
        )

    # ── SIN VALOR REAL PERO LAS MEJORES DEL DÍA ──
    else:
        lineas.append(
            "⛔ *HOY NO HAY PICKS CON VALOR REAL*\n"
            "He revisado todos los partidos y las cuotas de Bet365 "
            "no compensan el riesgo en ningún caso.\n"
        )

    if picks_sin_valor:
        lineas.append("─" * 30)
        lineas.append(
            "⚠️ *LAS MEJORES OPCIONES DE HOY "
            "(sin valor real, apostar con cuidado):*\n"
            "_Estas apuestas no cumplen el criterio de valor mínimo "
            "pero son las menos malas del día. "
            "Si decides apostar, hazlo con cantidades pequeñas._\n"
        )
        for pick in picks_sin_valor:
            lineas.append(explicar_pick(pick, es_sin_valor=True))

    # ── PARTIDOS SIN NADA RECOMENDABLE ──
    if sin_valor_nombres:
        lineas.append("─" * 30)
        lineas.append(f"❌ *PARTIDOS DESCARTADOS HOY ({len(sin_valor_nombres)}):*")
        lineas.append(", ".join(sin_valor_nombres))
        lineas.append("_(Cuotas muy por debajo de lo que merece el partido)_\n")

    lineas.append("─" * 30)
    lineas.append(f"📊 Total partidos analizados hoy: *{total}*")
    lineas.append(
        "⚠️ _Este análisis es orientativo. "
        "Las apuestas conllevan riesgo. "
        "Nunca apuestes más de lo que puedes permitirte perder._"
    )

    return "\n".join(lineas)

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=data)

if __name__ == "__main__":
    print("🔍 Recogiendo partidos del día...")
    partidos = obtener_cuotas()
    print(f"   → {len(partidos)} partidos encontrados")

    print("🧮 Calculando valor esperado...")
    picks, picks_sin_valor, sin_valor_nombres = analizar_partidos(partidos)
    print(f"   → {len(picks)} picks con valor real")
    print(f"   → {len(picks_sin_valor)} opciones sin valor pero recomendables")

    print("📱 Enviando a Telegram...")
    mensaje = construir_mensaje(picks, picks_sin_valor, sin_valor_nombres)
    enviar_telegram(mensaje)
    print("✅ ¡Listo!")
