from fastapi import FastAPI, Depends, HTTPException, Request, Form
import requests
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from passlib.context import CryptContext
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles


# FastAPI app
app = FastAPI()

# Static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database setup
DATABASE_URL = "sqlite:///./word_app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBasic()

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

class Word(Base):
    __tablename__ = "words"
    id = Column(Integer, primary_key=True, index=True)
    word = Column(String, unique=True, nullable=False)
    definition = Column(Text, nullable=False)
    user_id = Column(Integer, nullable=False)
    favorited_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Utils
def authenticate_user(db, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user or not pwd_context.verify(password, user.hashed_password):
        return False
    return user

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})





def hash_password(password: str) -> str:
    return pwd_context.hash(password)

@app.get("/create-user", response_class=HTMLResponse)
def show_create_user_form(request: Request):
    return templates.TemplateResponse("create_user.html", {"request": request})

@app.post("/create-user")
def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: SessionLocal = Depends(get_db)
):
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists.")

    # Hash the password and create the user
    hashed_password = hash_password(password)
    new_user = User(username=username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()

    # Redirect to login page after successful registration
    return RedirectResponse("/login", status_code=303)

@app.get("/lookup", response_class=HTMLResponse)
def lookup_word(request: Request, word: str = ""):
    if not word:
        return templates.TemplateResponse("index.html", {"request": request, "error": "Please enter a word."})

    api_url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return templates.TemplateResponse("index.html", {"request": request, "error": "An error occurred while fetching the definition."})

    # Parse API response
    definitions = []
    full_definition = ""
    for meaning in data[0]["meanings"]:
        part_of_speech = meaning["partOfSpeech"]
        for definition in meaning["definitions"]:
            definitions.append(
                {
                    "partOfSpeech": part_of_speech,
                    "definition": definition["definition"],
                    "example": definition.get("example", ""),
                }
            )
            full_definition += f"<b>{part_of_speech}:</b> {definition['definition']}<br>"
            if "example" in definition:
                full_definition += f"<i>Example:</i> {definition['example']}<br>"

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "word": word, "definitions": definitions, "full_definition": full_definition}
    )

@app.get("/login", response_class=HTMLResponse)
def show_login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: SessionLocal = Depends(get_db)
):
    user = authenticate_user(db, username, password)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("username", username)
    return response

@app.get("/favorites", response_class=HTMLResponse)
def get_favorites(request: Request, db: SessionLocal = Depends(get_db)):
    # Get the username from the cookie
    username = request.cookies.get("username")
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    # Retrieve the user
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    # Get the user's favorites
    favorites = db.query(Word).filter(Word.user_id == user.id).all()
    return templates.TemplateResponse("favorites.html", {"request": request, "favorites": favorites})

@app.post("/favorites")
def add_to_favorites(
    request: Request,
    word: str = Form(...),
    full_definition: str = Form(...),
    db: SessionLocal = Depends(get_db)
):
    # Get the username from the cookie
    username = request.cookies.get("username")
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    # Retrieve the user
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    # Check if the word is already in the user's favorites
    existing_word = db.query(Word).filter(Word.word == word, Word.user_id == user.id).first()
    if existing_word:
        raise HTTPException(status_code=400, detail="Word already in favorites.")

    # Add the word with the full definition to the database
    new_word = Word(word=word, definition=full_definition, user_id=user.id)
    db.add(new_word)
    db.commit()

    # Redirect back to the favorites page
    return RedirectResponse(url="/favorites", status_code=303)

@app.post("/favorites/remove")
def remove_from_favorites(
    request: Request,
    word: str = Form(...),
    db: SessionLocal = Depends(get_db)
):
    # Get the username from the cookie
    username = request.cookies.get("username")
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    # Retrieve the user
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    # Find the word in the user's favorites
    favorite_word = db.query(Word).filter(Word.word == word, Word.user_id == user.id).first()
    if not favorite_word:
        raise HTTPException(status_code=404, detail="Word not found in favorites.")

    # Remove the word from the database
    db.delete(favorite_word)
    db.commit()

    # Redirect back to the favorites page
    return RedirectResponse(url="/favorites", status_code=303)



@app.post("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=302)  # Redirect to home page
    response.delete_cookie("username")  # Remove the username cookie
    return response
