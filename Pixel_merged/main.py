from fastapi import FastAPI, Request, Cookie, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from copy import deepcopy
from uuid import uuid4
from noce import map_array  

import time

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class UserInfo:
    def __init__(self, carte):
        self.last_seen_map = deepcopy(carte)
        self.last_edited_time_nanos = 0  

class Carte:
    def __init__(self, nx: int, ny: int, timeout_nanos: int = 5_000_000_000):  # 5s
        self.keys = set()
        self.users = {}
        self.nx = nx
        self.ny = ny
        self.data = [[(0, 0, 0) for _ in range(nx)] for _ in range(ny)]
        self.timeout_nanos = timeout_nanos

    def create_new_key(self):
        key = str(uuid4())
        self.keys.add(key)
        return key

    def is_valid_key(self, key: str):
        return key in self.keys

    def create_new_user_id(self):
        user_id = str(uuid4())
        self.users[user_id] = UserInfo(self.data)
        return user_id

    def is_valid_user_id(self, user_id: str):
        return user_id in self.users

cartes = {
    "0000": Carte(nx=10, ny=10),
    "1234": Carte(nx=15, ny=15),
    "Noce": Carte(nx=50, ny=50)
}

# Une petite carte custom (merci la photo de profil github)
cartes["Noce"].data = map_array


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "cartes": list(cartes.keys())})

@app.get("/api/v1/{nom_carte}/preinit")
async def preinit(nom_carte: str):
    if nom_carte not in cartes:
        return JSONResponse({"error": "carte inconnue"}, status_code=404)
    carte = cartes[nom_carte]
    key = carte.create_new_key()
    res = JSONResponse({"key": key})
    res.set_cookie("key", key, secure=False, max_age=3600)
    return res

@app.get("/api/v1/{nom_carte}/init")
async def init(nom_carte: str, query_key: str = Query(alias="key"), cookie_key: str = Cookie(alias="key")):
    if nom_carte not in cartes:
        return JSONResponse({"error": "carte inconnue"}, status_code=404)
    carte = cartes[nom_carte]
    if query_key != cookie_key or not carte.is_valid_key(cookie_key):
        return JSONResponse({"error": "invalid key"}, status_code=400)
    user_id = carte.create_new_user_id()
    res = JSONResponse({
        "id": user_id,
        "nx": carte.nx,
        "ny": carte.ny,
        "timeout": carte.timeout_nanos // 1_000_000_000,
        "data": carte.data
    })
    res.set_cookie("id", user_id, secure=False, max_age=3600)
    return res

@app.get("/api/v1/{nom_carte}/deltas")
async def deltas(nom_carte: str, id: str = Query(...), key: str = Cookie(...)):
    if nom_carte not in cartes:
        return JSONResponse({"error": "carte inconnue"}, status_code=404)
    carte = cartes[nom_carte]
    if not carte.is_valid_key(key) or not carte.is_valid_user_id(id):
        return JSONResponse({"error": "invalid session"}, status_code=400)
    user_info = carte.users[id]
    deltas = []
    for y in range(carte.ny):
        for x in range(carte.nx):
            if carte.data[y][x] != user_info.last_seen_map[y][x]:
                r, g, b = carte.data[y][x]
                deltas.append([x, y, r, g, b])
                user_info.last_seen_map[y][x] = carte.data[y][x]
    return {"deltas": deltas}



@app.get("/api/v1/{nom_carte}/set")
async def set_pixel(nom_carte: str, x: int, y: int, r: int, g: int, b: int, id: str = Cookie(None), key: str = Cookie(None)):
    if nom_carte not in cartes:
        return JSONResponse({"error": "carte inconnue"}, status_code=404)
    carte = cartes[nom_carte]
    if not carte.is_valid_key(key) or not carte.is_valid_user_id(id):
        return JSONResponse({"error": "invalid session"}, status_code=400)



    user = carte.users[id]
    now = time.time_ns()
    if now - user.last_edited_time_nanos < carte.timeout_nanos:
        seconds_left = round((carte.timeout_nanos - (now - user.last_edited_time_nanos)) / 1_000_000_000)
        return JSONResponse({"error": f"cooldown", "retry_after": seconds_left}, status_code=429)


    if 0 <= x < carte.nx and 0 <= y < carte.ny:
        carte.data[y][x] = (r, g, b)
        user.last_edited_time_nanos = now
        return {"ok": True}
    else:
        return JSONResponse({"error": "coordonnées invalides"}, status_code=400)
