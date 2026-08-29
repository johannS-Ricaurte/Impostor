import json
import random
import string
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Banco de palabras categorizado
WORDS = {
    "Animales": ["Perro", "Gato", "Tigre", "Elefante", "Delfín", "Águila", "León", "Oso"],
    "Comida": ["Pizza", "Arepa", "Hamburguesa", "Sushi", "Tacos", "Pasta", "Empanada", "Paella"],
    "Lugares": ["Playa", "Colegio", "Hospital", "Aeropuerto", "Cine", "Parque", "Biblioteca", "Restaurante"]
}

# Almacenamiento en memoria
GAMES = {}

def generate_room_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if code not in GAMES:
            return code

def generate_player_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=12))

class ImpostorRequestHandler(BaseHTTPRequestHandler):

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filename, content_type):
        try:
            with open(filename, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "Archivo no encontrado")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._send_file("index.html", "text/html; charset=utf-8")
        elif path == "/style.css":
            self._send_file("style.css", "text/css; charset=utf-8")
        elif path == "/game.js":
            self._send_file("game.js", "application/javascript; charset=utf-8")
        elif path == "/state":
            query = urllib.parse.parse_qs(parsed.query)
            room_code = query.get("room", [None])[0]
            player_id = query.get("player_id", [None])[0]

            if not room_code or room_code not in GAMES:
                self._send_json({"error": "Sala no encontrada"}, status=404)
                return

            game = GAMES[room_code]

            # Actualizar lógica dependiente del tiempo
            self._update_game_timer(game)

            # Construir respuesta personalizada (Protección de datos privados)
            state = self._build_client_state(game, player_id)
            self._send_json(state)
        else:
            self.send_error(404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        path = self.path

        if path == "/create":
            player_name = data.get("name", "").strip()
            if not player_name:
                self._send_json({"error": "Nombre requerido"}, status=400)
                return

            room_code = generate_room_code()
            host_id = generate_player_id()

            GAMES[room_code] = {
                "room": room_code,
                "host_id": host_id,
                "status": "LOBBY", # LOBBY, ROLE_REVEAL, CLUES, VOTING, RESULTS
                "category": "Aleatoria",
                "impostor_count_setting": 0, # 0 = automático
                "word": "",
                "players": {
                    host_id: {"name": player_name, "is_impostor": False, "alive": True}
                },
                "turn_order": [],
                "current_turn_index": 0,
                "clues": {}, # player_id: text
                "votes": {}, # voter_id: target_id
                "tie_candidates": [], # Si hay empate en la votación
                "timer_end": 0,
                "winner": None,
                "eliminated_this_round": None
            }

            self._send_json({
                "room": room_code,
                "player_id": host_id
            })

        elif path == "/join":
            player_name = data.get("name", "").strip()
            room_code = data.get("room", "").strip().upper()

            if not player_name or not room_code:
                self._send_json({"error": "Nombre y código requeridos"}, status=400)
                return

            if room_code not in GAMES:
                self._send_json({"error": "La sala no existe"}, status=404)
                return

            game = GAMES[room_code]
            if game["status"] != "LOBBY":
                self._send_json({"error": "La partida ya ha comenzado"}, status=400)
                return

            player_id = generate_player_id()
            game["players"][player_id] = {
                "name": player_name,
                "is_impostor": False,
                "alive": True
            }

            self._send_json({
                "room": room_code,
                "player_id": player_id
            })

        elif path == "/start":
            room_code = data.get("room")
            player_id = data.get("player_id")
            category = data.get("category", "Aleatoria")
            impostor_count = int(data.get("impostor_count", 0))

            if room_code not in GAMES:
                self._send_json({"error": "Sala no encontrada"}, status=404)
                return

            game = GAMES[room_code]
            if game["host_id"] != player_id:
                self._send_json({"error": "Solo el host puede iniciar"}, status=403)
                return

            num_players = len(game["players"])
            if num_players < 3:
                self._send_json({"error": "Se necesitan al menos 3 jugadores"}, status=400)
                return

            # Calcular número de impostores
            if impostor_count == 0:
                if num_players <= 5:
                    calc_impostors = 1
                elif num_players <= 12:
                    calc_impostors = 2
                else:
                    calc_impostors = 3
            else:
                calc_impostors = impostor_count

            if calc_impostors >= num_players:
                self._send_json({"error": "No puede haber más impostores que jugadores"}, status=400)
                return

            # Seleccionar palabra
            if category == "Aleatoria" or category not in WORDS:
                cat_key = random.choice(list(WORDS.keys()))
            else:
                cat_key = category
            
            selected_word = random.choice(WORDS[cat_key])

            # Reiniciar estado de partida
            game["word"] = selected_word
            game["category"] = cat_key
            game["status"] = "ROLE_REVEAL"
            game["timer_end"] = time.time() + 10  # 10 segundos para ver rol
            game["clues"] = {}
            game["votes"] = {}
            game["tie_candidates"] = []
            game["winner"] = None
            game["eliminated_this_round"] = None

            # Asignar impostores
            player_ids = list(game["players"].keys())
            for pid in player_ids:
                game["players"][pid]["is_impostor"] = False
                game["players"][pid]["alive"] = True

            impostor_ids = random.sample(player_ids, calc_impostors)
            for imp_id in impostor_ids:
                game["players"][imp_id]["is_impostor"] = True

            # Configurar orden de turnos
            random.shuffle(player_ids)
            game["turn_order"] = player_ids
            game["current_turn_index"] = 0

            self._send_json({"success": True})

        elif path == "/clue":
            room_code = data.get("room")
            player_id = data.get("player_id")
            clue = data.get("clue", "").strip()

            if room_code not in GAMES:
                self._send_json({"error": "Sala no encontrada"}, status=404)
                return

            game = GAMES[room_code]
            if game["status"] != "CLUES":
                self._send_json({"error": "No estamos en fase de pistas"}, status=400)
                return

            current_turn_player = game["turn_order"][game["current_turn_index"]]
            if player_id != current_turn_player:
                self._send_json({"error": "No es tu turno"}, status=403)
                return

            if not clue:
                clue = "(Sin pista)"

            game["clues"][player_id] = clue
            self._advance_turn(game)
            self._send_json({"success": True})

        elif path == "/vote":
            room_code = data.get("room")
            voter_id = data.get("player_id")
            target_id = data.get("target_id")

            if room_code not in GAMES:
                self._send_json({"error": "Sala no encontrada"}, status=404)
                return

            game = GAMES[room_code]
            if game["status"] != "VOTING":
                self._send_json({"error": "No estamos en fase de votación"}, status=400)
                return

            if voter_id == target_id:
                self._send_json({"error": "No puedes votarte a ti mismo"}, status=400)
                return

            if game["tie_candidates"] and target_id not in game["tie_candidates"]:
                self._send_json({"error": "Debes votar por uno de los empatados"}, status=400)
                return

            game["votes"][voter_id] = target_id

            # Si todos los elegibles ya votaron, procesar inmediatamente
            eligible_voters = [p for p in game["players"] if game["players"][p]["alive"]]
            if len(game["votes"]) >= len(eligible_voters):
                self._process_voting_results(game)

            self._send_json({"success": True})

        elif path == "/new-round":
            room_code = data.get("room")
            player_id = data.get("player_id")

            if room_code not in GAMES:
                self._send_json({"error": "Sala no encontrada"}, status=404)
                return

            game = GAMES[room_code]
            if game["host_id"] != player_id:
                self._send_json({"error": "Solo el host puede iniciar nueva ronda"}, status=403)
                return

            game["status"] = "LOBBY"
            self._send_json({"success": True})

        else:
            self.send_error(404)

    # Lógica de gestión de turnos y temporizadores
    def _update_game_timer(self, game):
        now = time.time()
        if game["timer_end"] > 0 and now >= game["timer_end"]:
            if game["status"] == "ROLE_REVEAL":
                # Pasar a Pistas
                game["status"] = "CLUES"
                game["current_turn_index"] = 0
                game["timer_end"] = now + 30 # 30s para la primera pista
            elif game["status"] == "CLUES":
                # Forzar pista vacía si se agota el tiempo
                current_pid = game["turn_order"][game["current_turn_index"]]
                if current_pid not in game["clues"]:
                    game["clues"][current_pid] = "(Tiempo agotado)"
                self._advance_turn(game)
            elif game["status"] == "VOTING":
                # Procesar votación con los votos existentes
                self._process_voting_results(game)

    def _advance_turn(self, game):
        game["current_turn_index"] += 1
        # Buscar siguiente jugador vivo
        while game["current_turn_index"] < len(game["turn_order"]):
            pid = game["turn_order"][game["current_turn_index"]]
            if game["players"][pid]["alive"]:
                break
            game["current_turn_index"] += 1

        if game["current_turn_index"] >= len(game["turn_order"]):
            # Iniciar Votación
            game["status"] = "VOTING"
            game["votes"] = {}
            game["timer_end"] = time.time() + 45 # 45 segundos para votar
        else:
            game["timer_end"] = time.time() + 30 # Reset 30s por turno

    def _process_voting_results(self, game):
        vote_counts = {}
        for voter, target in game["votes"].items():
            vote_counts[target] = vote_counts.get(target, 0) + 1

        if not vote_counts:
            # Nadie votó, el impostor sobrevive
            self._check_win_condition(game, eliminated_id=None)
            return

        max_votes = max(vote_counts.values())
        most_voted = [pid for pid, count in vote_counts.items() if count == max_votes]

        if len(most_voted) == 1:
            # Eliminado único
            eliminated = most_voted[0]
            game["players"][eliminated]["alive"] = False
            game["eliminated_this_round"] = eliminated
            game["tie_candidates"] = []
            self._check_win_condition(game, eliminated_id=eliminated)
        else:
            # Empate
            if not game["tie_candidates"]:
                # Primer empate -> Segunda votación entre los empatados
                game["tie_candidates"] = most_voted
                game["votes"] = {}
                game["timer_end"] = time.time() + 45
            else:
                # Segundo empate -> Nadie es eliminado, el impostor sobrevive
                game["tie_candidates"] = []
                self._check_win_condition(game, eliminated_id=None)

    def _check_win_condition(self, game, eliminated_id):
        impostors_alive = sum(1 for p in game["players"].values() if p["is_impostor"] and p["alive"])
        normals_alive = sum(1 for p in game["players"].values() if not p["is_impostor"] and p["alive"])

        if impostors_alive == 0:
            game["winner"] = "JUGADORES"
            game["status"] = "RESULTS"
            game["timer_end"] = 0
        elif impostors_alive >= normals_alive:
            game["winner"] = "IMPOSTORES"
            game["status"] = "RESULTS"
            game["timer_end"] = 0
        else:
            # Continúa el juego con otra ronda de pistas
            game["status"] = "ROLE_REVEAL"
            game["timer_end"] = time.time() + 5
            # Reordenar turnos entre los vivos
            vivos = [p for p in game["turn_order"] if game["players"][p]["alive"]]
            game["turn_order"] = vivos
            game["current_turn_index"] = 0

    def _build_client_state(self, game, player_id):
        # PROTECCIÓN ABSOLUTA DE INFORMACIÓN PRIVADA
        player = game["players"].get(player_id)
        time_left = max(0, int(game["timer_end"] - time.time())) if game["timer_end"] > 0 else 0

        # Mapeo de jugadores sin revelar rol
        players_public = []
        for pid, pdata in game["players"].items():
            p_info = {
                "id": pid,
                "name": pdata["name"],
                "alive": pdata["alive"]
            }
            # Revelar rol solo al finalizar la partida
            if game["status"] == "RESULTS":
                p_info["is_impostor"] = pdata["is_impostor"]
            players_public.append(p_info)

        client_state = {
            "status": game["status"],
            "is_host": (game["host_id"] == player_id),
            "players": players_public,
            "category": game["category"],
            "time_left": time_left,
            "winner": game["winner"],
            "clues": game["clues"],
            "tie_candidates": game["tie_candidates"]
        }

        if game["status"] in ["CLUES", "VOTING"]:
            current_turn_pid = game["turn_order"][game["current_turn_index"]] if game["turn_order"] else None
            client_state["current_turn_id"] = current_turn_pid

        if game["status"] == "VOTING":
            client_state["has_voted"] = player_id in game["votes"]

        if game["status"] == "RESULTS":
            # Revelar votos al final
            client_state["votes"] = game["votes"]
            client_state["word"] = game["word"]

        # Control del ROL y la PALABRA por jugador
        if player:
            client_state["is_impostor"] = player["is_impostor"]
            if not player["is_impostor"] and game["status"] != "LOBBY":
                # Solo el jugador normal recibe la palabra
                client_state["word"] = game["word"]
            else:
                # El impostor NUNCA recibe la palabra
                client_state["word"] = None

        return client_state

def run():
    server_address = ('0.0.0.0', 8000)
    httpd = HTTPServer(server_address, ImpostorRequestHandler)
    print("Servidor iniciado en:")
    print("http://0.0.0.0:8000")
    httpd.serve_forever()

if __name__ == '__main__':
    run()