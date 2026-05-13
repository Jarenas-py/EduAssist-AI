from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from docxtpl import DocxTemplate, RichText
import google.generativeai as genai
import json
import os
import tempfile
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from fastapi import Depends
from database import engine, Base, get_db
from models import User

Base.metadata.create_all(bind=engine)
# Load environment variables
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')

class DocumentRequest(BaseModel):
    prompt: str
    user_id: Optional[int] = None
    

class UserRegister(BaseModel):
    firstName: str
    lastName: str
    email: str
    password: str
    position: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserUpdate(BaseModel):
    firstName: str
    lastName: str
    email: str
    password: str
    position: str

@app.post("/api/register")
def register_user(user: UserRegister, db: Session = Depends(get_db)):
    # Check if email is already taken
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    # Save the user exactly as they typed it
    new_user = User(
        first_name=user.firstName,
        last_name=user.lastName,
        email=user.email,
        password=user.password,
        position=user.position
    )
    db.add(new_user)
    db.commit()
    return {"message": "Registration successful"}

@app.post("/api/login")
def login_user(user: UserLogin, db: Session = Depends(get_db)):
    # Look for an exact match of email AND password
    db_user = db.query(User).filter(User.email == user.email, User.password == user.password).first()
    
    if not db_user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    # Return the user's database ID AND their first name!
    return {
        "user_id": db_user.id,
        "first_name": db_user.first_name
    }

@app.get("/api/user/{user_id}")
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Send the data back to the frontend
    return {
        "firstName": user.first_name,
        "lastName": user.last_name,
        "email": user.email,
        "password": user.password,
        "position": user.position
    }

@app.put("/api/user/{user_id}")
def update_user_profile(user_id: int, user_data: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update the database columns
    user.first_name = user_data.firstName
    user.last_name = user_data.lastName
    user.email = user_data.email
    user.password = user_data.password
    user.position = user_data.position
    
    db.commit()
    return {"message": "Profile updated successfully"}

@app.post("/api/generate-dll")
async def generate_dll(req: DocumentRequest, db: Session = Depends(get_db)):
    if not api_key:
        print("❌ ERROR: API Key is missing!")
        raise HTTPException(status_code=500, detail="Gemini API Key is missing.")
    
    # Check if a user ID was provided
    if req.user_id:
        user_profile = db.query(User).filter(User.id == req.user_id).first()
        if not user_profile:
             raise HTTPException(status_code=404, detail="User profile not found. Please log in again.")
             
        teacher_full_name = f"{user_profile.first_name} {user_profile.last_name}"
        school_name = user_profile.school_name
    else:
        # Default fallback for guest users
        teacher_full_name = "Juan Dela Cruz"
        school_name = "Las Piñas National High School"

    gemini_prompt = f"""
    You are an expert DepEd Philippines teacher assistant. 
    Based on this context: "{req.prompt}", generate a Banghay-Aralin (Daily Lesson Log).
    All content should be in Filipino (Tagalog) as per standard DepEd format, except when English is strictly required by the subject.
    
    You MUST respond with a raw JSON object containing EXACTLY these keys:
    "subject_name", "grade_level", "quarter", "teaching_week", "teaching_day", "teaching_date",
    "content_standards", "performance_standards", "learning_objectives", "values_developed", 
    "learning_skills", "content", "integration", "prior_knowledge", "lesson_purpose", 
    "lesson_development", "generalization", "evaluation", "reflection".
    
    AND an array called "annotations" containing objects with keys: "col1", "col2", "col3", "col4".
    """
    
    try:
        print("⏳ Asking Gemini Pro to generate lesson plan... (This may take 10-15 seconds)")
        response = model.generate_content(
            gemini_prompt,
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        
        # --- THE FIX: Strip out the markdown formatting ---
        clean_text = response.text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
            
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
            
        # Parse the cleaned string back into a Python dictionary
        ai_data = json.loads(clean_text.strip())
        print("✅ Gemini JSON successfully generated and cleaned!")
        
    except Exception as e:
        print(f"❌ AI GENERATION ERROR: {str(e)}")
        if 'response' in locals():
            print(f"Raw Gemini Output that caused crash: {response.text}")
        raise HTTPException(status_code=500, detail=f"AI Generation Failed: {str(e)}")

    try:
        print("⏳ Loading Word Template...")
        doc = DocxTemplate("DEPED_docs/DLL_Template.docx")
        print("✅ Template loaded!")
    except Exception as e:
        print(f"❌ TEMPLATE ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail="Template file not found on server.")

    # Map the AI data to your Jinja tags
    context = {
        "subject_name": ai_data.get("subject_name", ""),
        "grade_level": ai_data.get("grade_level", ""),
        "quarter": ai_data.get("quarter", ""),
        "teaching_week": ai_data.get("teaching_week", ""),
        "teaching_day": ai_data.get("teaching_day", ""),
        "teaching_date": ai_data.get("teaching_date", ""),
        
        "content_standards": RichText(ai_data.get("content_standards", "")),
        "performance_standards": RichText(ai_data.get("performance_standards", "")),
        "learning_objectives": RichText(ai_data.get("learning_objectives", "")),
        "values_developed": RichText(ai_data.get("values_developed", "")),
        "learning_skills": RichText(ai_data.get("learning_skills", "")),
        "content": RichText(ai_data.get("content", "")),
        "integration": RichText(ai_data.get("integration", "")),
        
        "prior_knowledge": RichText(ai_data.get("prior_knowledge", "")),
        "lesson_purpose": RichText(ai_data.get("lesson_purpose", "")),
        "lesson_development": RichText(ai_data.get("lesson_development", "")),
        "generalization": RichText(ai_data.get("generalization", "")),
        "evaluation": RichText(ai_data.get("evaluation", "")),
        "reflection": RichText(ai_data.get("reflection", "")),
        
        "annotations": ai_data.get("annotations", []),
        "teacher_name": teacher_full_name,
        "school_name": school_name
    }

    print("⏳ Injecting AI data into Word Document...")
    doc.render(context)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    doc.save(temp_file.name)
    print("🎉 Document successfully generated! Sending to browser...")

    return FileResponse(
        path=temp_file.name, 
        filename="EduAssist_Generated_DLL.docx", 
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )