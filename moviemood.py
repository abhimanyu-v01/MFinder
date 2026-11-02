#!/usr/bin/env python3
import os, sys, sqlite3, subprocess, requests
from guessit import guessit

MOVIE_DIR = os.path.expanduser("~/Movies")
DB = os.path.expanduser("~/.local/share/moviemood.db")
KEY = os.environ["TMDB_KEY"]
EXT = (".mkv", ".mp4", ".avi", ".webm")

GENRE_MOODS = {
    "Comedy": ["laugh", "light"], "Animation": ["light", "cozy"],
    "Family": ["cozy", "light"], "Romance": ["cozy"], "Music": ["cozy"],
    "Horror": ["scared"], "Thriller": ["tense"], "Crime": ["tense"],
    "Mystery": ["tense", "think"], "Science Fiction": ["think", "hype"],
    "Action": ["hype"], "Adventure": ["hype"], "Western": ["hype"],
    "Drama": ["heavy", "think"], "War": ["heavy"], "History": ["think"],
    "Documentary": ["think"], "Fantasy": ["escape"],
}
KEYWORD_MOODS = {"feel good": "light", "tearjerker": "heavy", "slasher": "scared"}

db = sqlite3.connect(DB)
db.execute("""CREATE TABLE IF NOT EXISTS movies(
    path TEXT PRIMARY KEY, title TEXT, year INT, runtime INT,
    rating REAL, genres TEXT, auto TEXT, manual TEXT DEFAULT '')""")

import time

def tmdb(path, **p):
    for attempt in range(4):
        try:
            r = requests.get(f"https://api.themoviedb.org/3/{path}",
                             params={"api_key": KEY, **p}, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            if attempt == 3:
                raise
            print(f"  retry {attempt+1} ({type(e).__name__})")
            time.sleep(2 * (attempt + 1))

def scan():
    known = {r[0] for r in db.execute("SELECT path FROM movies")}
    for root, _, files in os.walk(MOVIE_DIR):
        for f in files:
            full = os.path.join(root, f)
            if not f.lower().endswith(EXT) or full in known: continue
            g = guessit(f)
            hits = tmdb("search/movie", query=g.get("title", f), year=g.get("year", "")).get("results")
            if not hits:
                print("no match:", f); continue
            d = tmdb(f"movie/{hits[0]['id']}", append_to_response="keywords")
            genres = [x["name"] for x in d["genres"]]
            moods = {m for gn in genres for m in GENRE_MOODS.get(gn, [])}
            for k in d["keywords"]["keywords"]:
                if k["name"] in KEYWORD_MOODS: moods.add(KEYWORD_MOODS[k["name"]])
            db.execute("INSERT INTO movies VALUES(?,?,?,?,?,?,?,'')", (
                full, d["title"], int(d["release_date"][:4] or 0), d["runtime"],
                d["vote_average"], ",".join(genres), "," + ",".join(sorted(moods)) + ","))
            db.commit(); print("added:", d["title"])

def pick(mood, max_rt=999):
    rows = db.execute("""SELECT title, year, runtime, rating, path FROM movies
        WHERE runtime <= ? AND (CASE WHEN manual != '' THEN manual ELSE auto END) LIKE ?
        ORDER BY rating DESC""", (max_rt, f"%,{mood},%")).fetchall()
    if not rows: sys.exit("nothing for that mood")
    lines = "\n".join(f"{t} ({y}) {r}m ★{v:.1f}\t{p}" for t, y, r, v, p in rows)
    out = subprocess.run(["fzf", "--delimiter=\t", "--with-nth=1"],
                         input=lines, text=True, capture_output=True).stdout.strip()
    if out: subprocess.run(["mpv", out.split("\t")[1]])

def setmood(substr, moods):
    n = db.execute("UPDATE movies SET manual=? WHERE title LIKE ?",
                   ("," + moods + ",", f"%{substr}%")).rowcount
    db.commit(); print(f"updated {n}")

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["scan"]: scan()
    elif a[:1] == ["pick"]: pick(a[1], int(a[2]) if len(a) > 2 else 999)
    elif a[:1] == ["set"]: setmood(a[1], a[2])
    else: print("usage: scan | pick <mood> [max_minutes] | set <title-substr> mood1,mood2")
