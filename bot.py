import requests
import os
from datetime import datetime

# ─── TUS CLAVES (vienen de Railway, no las toques aquí) ──────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ODDS_API_KEY = os.environ["ODDS_API_KEY"]
RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]

# ─── LIGAS A ANALIZAR ────────────────────────────────────────────
LIGAS = [
    # Masculinas secundarias europeas
    "soccer_england_championship",
    "soccer_germany_bundesliga2",
    "soccer_italy_serie_b",
    "soccer_france_ligue_2",
    "soccer_spain_segunda_division",
    "soccer_netherlands_eredivisie",
    "soccer_belgium_first_div",
    # Femeninas
    "soccer_england_womens_super_league",
    "soccer_germany_frauen_bundesliga",
    "soccer_france_womens_d1",
    "soccer_spain_womens_primera",
    "soccer_italy_womens_serie_a",
    "soccer_usa_nwsl",
]

UMBRAL_EV = 0.05  # Mínimo 5% de valor esperado para recomendar

# ─── FUNCIONES ───────────────────────────────────────────────────

def obtener_cuotas():
    """Recoge todos los partidos de hoy con cuotas de Bet365"""
    partidos = []
    for liga in LIGAS:
        url = f"https://api.the-odds-api.com/v4/sports/{liga}/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "eu",
            "markets": "h2h",
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
    """Convierte el código técnico de la liga en un nombre legible"""
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
    """
    Valor Esperado = (probabilidad real × cuota) - 1
    Si es mayor que 0 → hay valor
    Ejemplo: prob 40% × cuota 3.00 = 1.20 → EV = +20%
    """
    return (prob_real * cuota) - 1

def estimar_probabilidades(local, visitante):
    """
    Estima la probabilidad real de cada resultado
    usando la forma reciente de ambos equipos.
    Si la API falla, usa probabilidades neutras estándar.
    """
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
                return 7  # valor neutro (47% victorias)
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

    pts_local = puntos_recientes(local)
    pts_visitante = puntos_recientes(visitante)
    total = pts_local + pts_visitante + 0.001

    # Ventaja de jugar en casa: +8%
    prob_local = min((pts_local / total) * 0.85 + 0.08, 0.75)
    prob_visitante = min((pts_visitante / total) * 0.85, 0.65)
    prob_empate = max(1 - prob_local - prob_visitante, 0.08)

    # Renormalizar para que sumen exactamente 1
    suma = prob_local + prob_empate + prob_visitante
    return {
        "local": round(prob_local / suma, 3),
        "empate": round(prob_empate / suma, 3),
        "visitante": round(prob_visitante / suma, 3),
    }

def analizar_partidos(partidos):
    """
    Para cada partido:
    1. Coge las cuotas de Bet365
    2. Estima las probabilidades reales
    3. Calcula el EV de cada resultado
    4. Si EV > 5% → pick con valor
    """
    picks_con_valor = []
    sin_valor = []

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

            mercados = bet365["markets"][0]["outcomes"]
            cuotas = {o["name"]: o["price"] for o in mercados}

            cuota_local = cuotas.get(local, 0)
            cuota_empate = cuotas.get("Draw", 0)
            cuota_visitante = cuotas.get(visitante, 0)

            if not all([cuota_local, cuota_empate, cuota_visitante]):
                continue

            probs = estimar_probabilidades(local, visitante)

            opciones = [
                ("🏠 Gana " + local, cuota_local, probs["local"]),
                ("🤝 Empate", cuota_empate, probs["empate"]),
                ("✈️ Gana " + visitante, cuota_visitante, probs["visitante"]),
            ]

            hay_valor = False
            for nombre, cuota, prob in opciones:
                ev = calcular_ev(prob, cuota)
                if ev >= UMBRAL_EV:
                    picks_con_valor.append({
                        "partido": f"{local} vs {visitante}",
                        "liga": nombre_liga(liga),
                        "mercado": nombre,
                        "cuota": cuota,
                        "prob_real": round(prob * 100, 1),
                        "ev": round(ev * 100, 1),
                    })
                    hay_valor = True

            if not hay_valor:
                sin_valor.append(f"{local} vs {visitante}")

        except Exception:
            continue

    picks_con_valor.sort(key=lambda x: x["ev"], reverse=True)
    return picks_con_valor[:5], sin_valor

def explicar_pick(pick, es_el_mejor=False):
    """
    Explica cada pick en lenguaje completamente sencillo.
    Sin tecnicismos, como si se lo contaras a un amigo.
    """
    partido = pick["partido"]
    mercado = pick["mercado"]
    cuota = pick["cuota"]
    prob = pick["prob_real"]
    ev = pick["ev"]
    liga = pick["liga"]

    if ev >= 20:
        nivel = "🔥 VALOR MUY ALTO"
        explicacion_ev = f"Por cada 10€ apostados, matemáticamente deberías ganar {round(ev/10, 1)}€ a largo plazo."
    elif ev >= 10:
        nivel = "✅ VALOR ALTO"
        explicacion_ev = f"La cuota paga bastante más de lo que debería. Hay margen claro de beneficio."
    else:
        nivel = "👍 VALOR MODERADO"
        explicacion_ev = f"La cuota es algo mejor de lo justo. Vale la pena pero sin exagerar la apuesta."

    estrella = "⭐ MEJOR APUESTA DEL DÍA\n" if es_el_mejor else ""

    return (
        f"{estrella}"
        f"*{partido}*\n"
        f"🏆 Liga: {liga}\n"
        f"📌 Qué apostamos: {mercado}\n"
        f"💰 Cuota en Bet365: {cuota}\n"
        f"📊 Probabilidad real estimada: {prob}%\n"
        f"📈 Nivel de valor: {nivel} (+{ev}%)\n"
        f"💡 En cristiano: {explicacion_ev}\n"
    )

def construir_mensaje(picks, sin_valor):
    """
    Construye el mensaje completo que recibirás en Telegram.
    """
    hoy = datetime.now().strftime("%A %d de %B de %Y").upper()
    total = len(picks) + len(sin_valor)
    lineas = [
        f"🎯 *ANÁLISIS DE APUESTAS*",
        f"📅 {hoy}\n",
    ]

    if picks:
        lineas.append(f"✅ *{len(picks)} PICKS CON VALOR ENCONTRADOS HOY:*\n")
        for i, pick in enumerate(picks):
            es_mejor = (i == 0)
            lineas.append(explicar_pick(pick, es_el_mejor=es_mejor))

        # La apuesta más recomendable del día
        mejor = picks[0]
        lineas.append("─" * 30)
        lineas.append(
            f"⭐ *LA APUESTA MÁS RECOMENDABLE HOY:*\n"
            f"Partido: *{mejor['partido']}*\n"
            f"Qué hacer: Apostar a *{mejor['mercado']}*\n"
            f"Cuota: *{mejor['cuota']}* en Bet365\n"
            f"Por qué: De todos los partidos analizados hoy, "
            f"este tiene el mayor desfase entre lo que paga Bet365 "
            f"y lo que realmente merece el partido. "
            f"Un valor esperado de +{mejor['ev']}% significa que "
            f"la casa de apuestas está pagando más de lo que debería "
            f"→ eso es exactamente lo que buscamos.\n"
        )
    else:
        lineas.append(
            "⛔ *HOY NO HAY PICKS CON VALOR*\n\n"
            "He revisado todos los partidos disponibles y las cuotas "
            "de Bet365 no compensan el riesgo real en ningún caso. "
            "Mejor no apostar hoy. Mañana habrá más oportunidades.\n"
        )

    if sin_valor:
        lineas.append("─" * 30)
        lineas.append(f"❌ *PARTIDOS ANALIZADOS SIN VALOR ({len(sin_valor)}):*")
        lineas.append(", ".join(sin_valor))
        lineas.append("_(Las cuotas de estos partidos no son suficientemente buenas)_\n")

    lineas.append("─" * 30)
    lineas.append(f"📊 Total partidos analizados hoy: *{total}*")
    lineas.append(
        "⚠️ _Este análisis es orientativo. "
        "Las apuestas conllevan riesgo. "
        "Nunca apuestes más de lo que puedes permitirte perder._"
    )

    return "\n".join(lineas)

def enviar_telegram(mensaje):
    """Envía el mensaje a tu Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=data)

# ─── EJECUCIÓN ───────────────────────────────────────────────────
if __name__ == "__main__":
    print("🔍 Recogiendo partidos del día...")
    partidos = obtener_cuotas()
    print(f"   → {len(partidos)} partidos encontrados")

    print("🧮 Calculando valor esperado...")
    picks, sin_valor = analizar_partidos(partidos)
    print(f"   → {len(picks)} picks con valor detectados")

    print("📱 Enviando a Telegram...")
    mensaje = construir_mensaje(picks, sin_valor)
    enviar_telegram(mensaje)
    print("✅ ¡Listo!")
