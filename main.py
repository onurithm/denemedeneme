import os
from datetime import datetime, date
import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google import genai
import requests

# Supabase REST Wrapper to bypass pyiceberg/C++ build errors
class SupabaseRestResponse:
    def __init__(self, data):
        self.data = data

    @property
    def user(self):
        class _User:
            def __init__(self, d):
                self.id = d.get("id") or d.get("sub")
        data_to_use = self.data.get("user") if "user" in (self.data or {}) else self.data
        if not data_to_use or ("id" not in data_to_use and "sub" not in data_to_use):
            return None
        return _User(data_to_use)
    
    @property
    def session(self):
        class _Session:
            def __init__(self, access_token):
                self.access_token = access_token
        session_data = self.data.get("session") if self.data else None
        if session_data:
            return _Session(session_data.get("access_token"))
        elif self.data and "access_token" in self.data:
            return _Session(self.data.get("access_token"))
        return None

class SupabaseAuth:
    def __init__(self, url, key, headers):
        self.url = url
        self.key = key
        self.headers = headers

    def sign_up(self, credentials):
        res = requests.post(f"{self.url}/auth/v1/signup", headers=self.headers, json=credentials)
        if res.status_code >= 400:
            raise Exception(res.text)
        return SupabaseRestResponse(res.json())

    def sign_in_with_password(self, credentials):
        res = requests.post(f"{self.url}/auth/v1/token?grant_type=password", headers=self.headers, json=credentials)
        if res.status_code >= 400:
            raise Exception("Invalid credentials")
        return SupabaseRestResponse(res.json())

    def get_user(self, token):
        headers = dict(self.headers)
        headers["Authorization"] = f"Bearer {token}"
        res = requests.get(f"{self.url}/auth/v1/user", headers=headers)
        if res.status_code >= 400:
            return None
        return SupabaseRestResponse(res.json())

class SupabaseTableQueryBuilder:
    def __init__(self, url, headers, table):
        self.url = url
        self.headers = headers
        self.table = table
        self._select = None
        self._eq = {}
        self._gte = {}
        self._single = False
    
    def select(self, columns="*"):
        self._select = columns
        return self

    def insert(self, data):
        self._insert_data = data
        return self

    def delete(self):
        self._delete = True
        return self

    def eq(self, column, value):
        self._eq[column] = value
        return self

    def gte(self, column, value):
        self._gte[column] = value
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        if hasattr(self, '_insert_data'):
            headers = dict(self.headers)
            headers["Prefer"] = "return=representation"
            res = requests.post(f"{self.url}/rest/v1/{self.table}", headers=headers, json=self._insert_data)
            if res.status_code >= 400:
                raise Exception(res.text)
            return SupabaseRestResponse(res.json())
            
        elif hasattr(self, '_delete'):
            params = {}
            for k, v in self._eq.items():
                params[k] = f"eq.{v}"
            res = requests.delete(f"{self.url}/rest/v1/{self.table}", headers=self.headers, params=params)
            if res.status_code >= 400:
                raise Exception(res.text)
            return SupabaseRestResponse(None)
            
        else:
            params = {"select": self._select} if self._select else {}
            for k, v in self._eq.items():
                params[k] = f"eq.{v}"
            for k, v in self._gte.items():
                params[k] = f"gte.{v}"
            
            res = requests.get(f"{self.url}/rest/v1/{self.table}", headers=self.headers, params=params)
            if res.status_code >= 400:
                raise Exception(res.text)
            data = res.json()
            if self._single and len(data) > 0:
                data = data[0]
            return SupabaseRestResponse(data)

class SimpleSupabaseClient:
    def __init__(self, url, key):
        self.url = url
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        self.auth = SupabaseAuth(url, key, self.headers)

    def table(self, table_name, token=None):
        headers = dict(self.headers)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return SupabaseTableQueryBuilder(self.url, headers, table_name)


app = FastAPI(title="FitTrack API")

# CORS Settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase Configurations
SUPABASE_URL = "https://andvpqqvkoetvpcojrjr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFuZHZwcXF2a29ldHZwY29qcmpyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE4OTc2MTEsImV4cCI6MjA4NzQ3MzYxMX0.VgvNVSeIl4EzCT37pyhB4yXt6xSYqUjhH0AcbftUcRg"
supabase = SimpleSupabaseClient(SUPABASE_URL, SUPABASE_KEY)

# Gemini AI Configurations
# The new google-genai client
gemini_client = genai.Client(api_key="AIzaSyCgAIm9enfEIgO0qUhtTD3K6tTmSsOvjFQ")

# Authentication Dependency
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Geçersiz token")
        return user_response.user
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Oturum süresi doldu veya yetkisiz erişim: {str(e)}")


# Models
class RegisterRequest(BaseModel):
    email: str
    password: str
    username: str

class LoginRequest(BaseModel):
    email: str
    password: str

class WorkoutRequest(BaseModel):
    exercise_id: str
    sets: int
    reps: int
    weight_kg: float
    workout_date: date
    notes: str = ""

# --- API Endpoints ---

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    try:
        res = supabase.auth.sign_up({
            "email": req.email, 
            "password": req.password,
            "options": {"data": {"dummy": "data"}} # Helps avoid strict email rate limits if unverified
        })
        if res.user:
            supabase.table('profiles').insert({"id": res.user.id, "username": req.username}).execute()
        return {"access_token": res.session.access_token if res.session else None}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    try:
        res = supabase.auth.sign_in_with_password({"email": req.email, "password": req.password})
        return {"access_token": res.session.access_token}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Giriş başarısız. Lütfen bilgilerinizi kontrol edin.")

@app.get("/api/profile")
async def get_profile(user = Depends(get_current_user), credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        res = supabase.table("profiles", token=credentials.credentials).select("*").eq("id", user.id).single().execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/exercises")
async def get_exercises(user = Depends(get_current_user), credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        res = supabase.table("exercises", token=credentials.credentials).select("*").execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/workouts")
async def create_workout(req: WorkoutRequest, user = Depends(get_current_user), credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        data = dict(req)
        data["user_id"] = user.id
        data["workout_date"] = data["workout_date"].isoformat()
        res = supabase.table("workouts", token=credentials.credentials).insert(data).execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/workouts")
async def get_workouts(user = Depends(get_current_user), credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        res = supabase.table("workouts", token=credentials.credentials).select("*, exercises(name, muscle_group)").eq("user_id", user.id).execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/workouts/history")
async def get_workouts_history(user = Depends(get_current_user), credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        res = supabase.table("workouts", token=credentials.credentials).select("*, exercises(name, muscle_group)").eq("user_id", user.id).execute()
        # Sort descending by date and time
        data = sorted(res.data, key=lambda x: (x["workout_date"], x["created_at"]), reverse=True)
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/workouts/{workout_id}")
async def delete_workout(workout_id: str, user = Depends(get_current_user), credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        res = supabase.table("workouts", token=credentials.credentials).delete().eq("id", workout_id).eq("user_id", user.id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/stats")
async def get_stats(user = Depends(get_current_user), credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        workouts_req = supabase.table("workouts", token=credentials.credentials).select("*, exercises(name)").eq("user_id", user.id).execute()
        workouts = workouts_req.data
        
        total_workouts = len(workouts)
        total_exercises = len(set(w["exercise_id"] for w in workouts))
        
        from datetime import timedelta
        week_ago = date.today() - timedelta(days=7)
        this_week_workouts = len([w for w in workouts if date.fromisoformat(w["workout_date"]) >= week_ago])
        
        from collections import Counter
        most_used_exercise = ""
        if workouts:
            ex_names = [w.get("exercises", {}).get("name") for w in workouts if w.get("exercises")]
            if ex_names:
                most_used_exercise = Counter(ex_names).most_common(1)[0][0]
        
        recent_workouts = sorted(workouts, key=lambda x: x["workout_date"], reverse=True)[:5]
        
        progress_by_exercise = {}
        for w in workouts:
            ex_name = w.get("exercises", {}).get("name") if w.get("exercises") else "Bilinmeyen"
            if ex_name not in progress_by_exercise:
                progress_by_exercise[ex_name] = []
            progress_by_exercise[ex_name].append({
                "date": w["workout_date"],
                "weight": w["weight_kg"]
            })
            
        for ex in progress_by_exercise:
            progress_by_exercise[ex] = sorted(progress_by_exercise[ex], key=lambda x: x["date"])
            
        return {
            "total_workouts": total_workouts,
            "total_exercises": total_exercises,
            "this_week_workouts": this_week_workouts,
            "most_used_exercise": most_used_exercise,
            "recent_workouts": recent_workouts,
            "progress_by_exercise": progress_by_exercise
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/ai/analysis")
async def get_ai_analysis(user = Depends(get_current_user), credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        from datetime import timedelta
        thirty_days_ago = (date.today() - timedelta(days=30)).isoformat()
        workouts_req = supabase.table("workouts", token=credentials.credentials).select("*, exercises(name, muscle_group)").eq("user_id", user.id).gte("workout_date", thirty_days_ago).execute()
        workouts = workouts_req.data
        
        if not workouts:
            return {"analysis": "Henüz yeterli antrenman veriniz bulunmuyor. Düzenli antrenman yapmaya başladıktan sonra buradan yapay zeka analizi alabilirsiniz!"}
        
        prompt_data = "Kullanıcının son 30 günlük antrenman verileri:\n"
        for w in workouts:
            ex_name = w.get("exercises", {}).get("name") if w.get("exercises") else "Bilinmeyen"
            prompt_data += f"- Tarih: {w['workout_date']}, Egzersiz: {ex_name}, Set: {w['sets']}, Tekrar: {w['reps']}, Ağırlık: {w['weight_kg']} kg\n"
            
        system_prompt = "Sen bir kişisel fitness koçusun. Kullanıcının antrenman verilerini analiz edip Türkçe olarak güçlü yönlerini, gelişim alanlarını ve önümüzdeki hafta için somut öneriler ver. Maksimum 300 kelime, samimi ve motive edici bir ton kullan."
        
        full_prompt = f"{system_prompt}\n\n{prompt_data}"
        response = gemini_client.models.generate_content(
            model="gemini-3-flash-preview", 
            contents=full_prompt
        )
        
        return {"analysis": response.text}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Static File Serving ---

# 'static' dizini yoksa oluştur
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")

@app.get("/dashboard")
async def serve_dashboard():
    return FileResponse("static/dashboard.html")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
