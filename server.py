import random
import os
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Configuration CORS pour permettre les requêtes depuis le front-end
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # À restreindre en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

clients: Dict[WebSocket, str] = {}  # Stocke les clients et leur ID
players: Dict[str, dict] = {}  # Stocke les joueurs avec leurs cartes

def generate_deck():
    """ Génère un deck de 52 cartes avec des valeurs numériques. """
    values = [str(i) for i in range(2, 15)]  # 11 = J, 12 = Q, 13 = K, 14 = A
    suits = ["hearts", "diamonds", "clubs", "spades"]
    return [{"value": v, "suit": s} for v in values for s in suits]

def save_game_state(code, game_data):
    """ Sauvegarde l'état du jeu en JSON. """
    if not os.path.exists("games"):
        os.makedirs("games")
    with open(f"games/{code}.json", "w") as f:
        json.dump(game_data, f, indent=4)

def load_game_state(code):
    """ Charge l'état du jeu depuis un fichier JSON. """
    file_path = f"games/{code}.json"
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return None

@app.get("/game/{code}")
async def get_game_state(code: str):
    game_data = load_game_state(code)
    print(f"Requête pour /game/{code} → Données envoyées :", game_data)  # 🔹 Ajout du log
    if not game_data:
        return {"error": "Game not found"}
    return game_data

def get_active_games():
    """ Récupère les parties actives. """
    games = []
    if os.path.exists("games"):
        for file in os.listdir("games"):
            if file.endswith(".json"):
                code = file.replace(".json", "")
                game_data = load_game_state(code)
                if game_data:
                    games.append({"code": code, "players": len(game_data["players"])})
    return games

@app.get("/games")
async def list_games():
    return get_active_games()

@app.post("/create-game")
async def create_game(data: dict):
    username = data.get("username")
    if not username:
        return {"error": "Username is required"}
    
    code = str(random.randint(1000, 9999))
    deck = generate_deck()
    random.shuffle(deck)
    
    game_data = {
        "players": [{
            "id": 1,
            "username": username,
            "ready":False,
            "hand_card": deck[:3],
            "front_card": deck[3:6],
            "back_card": deck[6:9]
     }],
    "pioche": deck[9:],  # Le reste du deck devient la pioche
    "playArea": [],
    "currentTurnIndex": 0,
    "nextComparison": None,
    "gameStarted": False
}
    
    save_game_state(code, game_data)
    return {"code": code}

@app.post("/join-game/{code}")
async def join_game(code: str, data: dict):
    username = data.get("username")
    if not username:
        return {"error": "Username is required"}
     
    game_data = load_game_state(code)
    if not game_data:
        return {"error": "Game not found"}
    
    if any(player["username"] == username for player in game_data["players"]):
        return {"error": "Username already taken"}
    
    if len(game_data["players"]) >= 5:
        return {"error": "Game is full"}
    
    player_id = len(game_data["players"]) + 1
    deck = game_data["pioche"]
    
    new_player = {
        "id": player_id,
        "username": username,
        "ready": False,
        "hand_card": deck[:3],
        "front_card": deck[3:6],
        "back_card": deck[6:9]
    }
    
    game_data["players"].append(new_player)
    game_data["pioche"] = deck[9:]

    # 🔴 (AJOUT IMPORTANT) Vérifie et initialise les clés manquantes
    game_data.setdefault("playArea", [])
    game_data.setdefault("currentTurnIndex", 0)
    game_data.setdefault("nextComparison", None)
    game_data.setdefault("gameStarted", False)

    save_game_state(code, game_data)
    
    return {"success": True}



@app.post("/update-game/{code}")
async def update_game(code: str, data: dict):
    """
    Met à jour l'état du jeu avec les données envoyées par le client.
    Le serveur ne vérifie pas la validité des règles.
    """
    save_game_state(code, data)
    return {"success": True}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    player_id = str(len(players) + 1)
    clients[websocket] = player_id
    players[player_id] = {}

    try:
        while True:
            await websocket.receive_json()
    except WebSocketDisconnect:
        del players[player_id]
        del clients[websocket]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
