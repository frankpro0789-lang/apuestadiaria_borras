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
    """
    Recoge TODAS las opciones de todos los partidos,
    las ordena por EV de mayor a menor,
    y devuelve siempre las 5 mejores pase lo que pase.
    """
    todas_las_opciones = []

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
                    todas_las_opciones.append({
                        "partido": f"{local} vs {visitante}",
                        "liga": nombre_liga(liga),
                        "mercado": nombre,
                        "categoria": categoria,
                        "cuota": cuota,
                        "prob_real": round(prob * 100, 1),
                        "ev": round(ev * 100, 1),
                        "tiene_valor": ev >= 0.05,
                    })

        except Exception:
            continue

    # Ordenar todas por EV de mayor a menor
    todas_las_opciones.sort(key=lambda x: x["ev"], reverse=True)

    # Coger siempre las 5 mejores
    top5 = todas_las_opciones[:5]

    return top5

def etiqueta_pick(pick, numero):
    ev = pick["ev"]
    tiene_valor = pick["tiene_valor"]

    if tiene_valor:
        if ev >= 20:
            nivel = "🔥 VALOR MUY ALTO"
            explicacion = f"Por cada 10€ apostados, matemáticamente deberías ganar {round(ev/10,1)}€ a largo plazo."
        elif ev >= 10:
            nivel = "✅ VALOR ALTO"
            explicacion = "Bet365 paga bastante más de lo que debería. Buen margen de beneficio."
        else:
            nivel = "👍 VALOR MODERADO"
            explicacion = "La cuota es mejor de lo justo. Vale la pena apostar."
    else:
        if ev >= 0:
            nivel = "⚠️ SIN VALOR — Cuota justa"
            explicacion = "Bet365 paga aproximadamente lo correcto. No hay ventaja matemática pero tampoco desventaja grande."
        elif ev >= -5:
            nivel = "⚠️ SIN VALOR — Cuota algo baja"
            explicacion = "Bet365 paga un poco menos de lo que debería. Es la mejor opción disponible hoy pero apuesta poco."
        else:
            nivel = "🔴 SIN VALOR — Cuota baja"
            explicacion = "Bet365 paga claramente menos de lo que merece. Solo se incluye porque es lo mejor disponible hoy. Cuidado."

    estrella = "⭐ MEJOR APUESTA DEL DÍA\n" if numero == 1 else ""

    return (
        f"{estrella}"
        f"*Pick {numero}: {pick['partido']}*\n"
        f"🏆 Liga: {pick['liga']}\n"
        f"📌 Mercado: {pick['mercado']}\n"
        f"💰 Cuota Bet365: {pick['cuota']}\n"
        f"📊 Probabilidad real estimada: {pick['prob_real']}%\n"
        f"📈 Nivel: {nivel} ({'+' if ev >= 0 else ''}{ev}%)\n"
        f"💡 En cristiano: {explicacion}\n"
    )

def construir_mensaje(picks):
    hoy = datetime.now().strftime("%A %d de %B de %Y").upper()
    picks_con_valor = [p for p in picks if p["tiene_valor"]]
    picks_relleno = [p for p in picks if not p["tiene_valor"]]

    lineas = [
        f"🎯 *ANÁLISIS DE APUESTAS*",
        f"📅 {hoy}\n",
    ]

    if picks_con_valor:
        lineas.append(f"✅ *{len(picks_con_valor)} apuesta(s) con valor real detectadas hoy*")
    else:
        lineas.append("⛔ *Hoy no hay apuestas con valor real*")
        lineas.append("_Aun así te mando las 5 mejores opciones disponibles._\n")

    lineas.append("─" * 30 + "\n")

    for i, pick in enumerate(picks, 1):
        lineas.append(etiqueta_pick(pick, i))

    # Resumen final — la más recomendable
    mejor = picks[0]
    lineas.append("─" * 30)
    lineas.append(
        f"⭐ *LA MÁS RECOMENDABLE HOY:*\n"
        f"Partido: *{mejor['partido']}*\n"
        f"Apuesta: *{mejor['mercado']}*\n"
        f"Cuota: *{mejor['cuota']}* en Bet365\n"
        f"Por qué es la mejor: Tiene el EV más alto de todos los partidos "
        f"analizados hoy ({'+' if mejor['ev'] >= 0 else ''}{mejor['ev']}%). "
        f"{'Bet365 está pagando más de lo que debería → ventaja matemática a tu favor.' if mejor['tiene_valor'] else 'Aunque no hay valor perfecto hoy, esta es la menos mala de todas las opciones disponibles.'}\n"
    )

    lineas.append("─" * 30)
    lineas.append("⚠️ _Este análisis es orientativo. Las apuestas conllevan riesgo. Nunca apuestes más de lo que puedes permitirte perder._")

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

    print("🧮 Analizando y seleccionando las 5 mejores opciones...")
    picks = analizar_partidos(partidos)
    print(f"   → {len(picks)} picks seleccionados")
    print(f"   → {sum(1 for p in picks if p['tiene_valor'])} con valor real")

    print("📱 Enviando a Telegram...")
    mensaje = construir_mensaje(picks)
    enviar_telegram(mensaje)
    print("✅ ¡Listo!")
