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
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

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
    template_type: Optional[str] = "dll" 
    user_id: Optional[int] = None
    
class UserRegister(BaseModel):
    firstName: str
    middleName: Optional[str] = None
    lastName: str
    dob: str
    email: str
    password: str
    position: str
    schoolName: str
    phone1: str
    phone2: Optional[str] = None
    blockLot: Optional[str] = None
    street: str
    village: str
    city: str
    region: str
    zip: str
    country: Optional[str] = "Philippines"

class UserLogin(BaseModel):
    email: str
    password: str

class UserUpdate(BaseModel):
    firstName: str
    middleName: Optional[str] = None
    lastName: str
    dob: str
    email: str
    password: str
    position: str
    schoolName: str
    phone1: str
    phone2: Optional[str] = None
    blockLot: Optional[str] = None
    street: str
    village: str
    city: str
    region: str
    zip: str
    country: Optional[str] = "Philippines"

@app.post("/api/register")
def register_user(user: UserRegister, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    new_user = User(
        first_name=user.firstName, middle_name=user.middleName, last_name=user.lastName,
        dob=user.dob, email=user.email, password=user.password, position=user.position,
        school_name=user.schoolName, phone1=user.phone1, phone2=user.phone2,
        block_lot=user.blockLot, street=user.street, village=user.village,
        city=user.city, region=user.region, zip_code=user.zip, country=user.country
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
    
    return {
        "firstName": user.first_name, "middleName": user.middle_name, "lastName": user.last_name,
        "dob": user.dob, "email": user.email, "password": user.password, "position": user.position,
        "schoolName": user.school_name, "phone1": user.phone1, "phone2": user.phone2,
        "blockLot": user.block_lot, "street": user.street, "village": user.village,
        "city": user.city, "region": user.region, "zip": user.zip_code, "country": user.country
    }

@app.put("/api/user/{user_id}")
def update_user_profile(user_id: int, user_data: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.first_name = user_data.firstName
    user.middle_name = user_data.middleName
    user.last_name = user_data.lastName
    user.dob = user_data.dob
    user.email = user_data.email
    user.password = user_data.password
    user.position = user_data.position
    user.school_name = user_data.schoolName
    user.phone1 = user_data.phone1
    user.phone2 = user_data.phone2
    user.block_lot = user_data.blockLot
    user.street = user_data.street
    user.village = user_data.village
    user.city = user_data.city
    user.region = user_data.region
    user.zip_code = user_data.zip
    user.country = user_data.country
    
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

    if req.template_type == "narrative":
        gemini_prompt = f"""
        You are an expert DepEd Philippines teacher assistant. 
        Based on this context: "{req.prompt}", generate a Narrative Report.
        
        You MUST respond with a raw JSON object containing EXACTLY these keys:
        "term_year", "session_topic", "session_speaker", "date_time", "session_venue", "narrative_report",
        AND an array called "attendance" containing objects with EXACTLY these keys: "attendee_name", "attendee_position".
        """
        template_file = "DEPED_docs/NarrativeReport_Template.docx"

    elif req.template_type == "proposal":
        gemini_prompt = f"""
        You are an expert DepEd Philippines teacher assistant. 
        Based on this context: "{req.prompt}", generate an Activity Proposal.
        
        You MUST respond with a raw JSON object containing EXACTLY these keys:
        "proposal_title", "activity_title", "proposal_rationale", "proposal_objectives", 
        "proposal_data", "proposal_activities", "proposal_venue", "proposal_participants", 
        "proposal_output", "proposal_monitoring", "endorsement_date", "principal_name", 
        "principal_position", "term_year", "total_amount",
        AND 4 arrays:
        "pre_implementation" (objects with keys: "item_date", "item_activity", "item_platform"),
        "implementation" (objects with keys: "item_date", "item_activity", "item_venue"),
        "post_implementation" (objects with keys: "item_date", "item_activity", "item_platform"),
        "funding" (objects with keys: "item_details", "item_amount", "item_source").
        """
        template_file = "DEPED_docs/Proposal_Template.docx"
        
    else: # Default to DLL
        gemini_prompt = f"""
        You are an expert DepEd Philippines teacher assistant. 
        Based on this context: "{req.prompt}", generate a Banghay-Aralin (Daily Lesson Log).
        All content should be in Filipino (Tagalog) as per standard DepEd format.
        
        You MUST respond with a raw JSON object containing EXACTLY these keys:
        "subject_name", "grade_level", "quarter", "teaching_week", "teaching_day", "teaching_date",
        "content_standards", "performance_standards", "learning_objectives", "values_developed", 
        "learning_skills", "content", "integration", "prior_knowledge", "lesson_purpose", 
        "lesson_development", "generalization", "evaluation", "reflection".
        AND an array called "annotations" containing objects with keys: "col1", "col2", "col3", "col4".
        """
        template_file = "DEPED_docs/DLL_Template.docx"
    
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
        print(f"⏳ Loading Word Template: {template_file}...")
        doc = DocxTemplate(template_file)
        print("✅ Template loaded!")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Template file not found on server.") 

    # Map the AI data to your Jinja tags
    first_name_db = user_profile.first_name if req.user_id else "Juan"
    last_name_db = user_profile.last_name if req.user_id else "Dela Cruz"
    position_db = user_profile.position if req.user_id else "Teacher I"

    if req.template_type == "narrative":
        context = {
            "term_year": ai_data.get("term_year", ""),
            "session_topic": ai_data.get("session_topic", ""),
            "session_speaker": ai_data.get("session_speaker", ""),
            "date_time": ai_data.get("date_time", ""),
            "session_venue": ai_data.get("session_venue", ""),
            "attendance": ai_data.get("attendance", []),
            "narrative_report": RichText(ai_data.get("narrative_report", "")),
            "first_name": first_name_db,
            "last_name": last_name_db,
            "position": position_db
        }
    elif req.template_type == "proposal":
        context = {
            "proposal_title": ai_data.get("proposal_title", ""),
            "activity_title": ai_data.get("activity_title", ""),
            "proposal_rationale": RichText(ai_data.get("proposal_rationale", "")),
            "proposal_objectives": RichText(ai_data.get("proposal_objectives", "")),
            "proposal_data": ai_data.get("proposal_data", ""),
            "proposal_activities": ai_data.get("proposal_activities", ""),
            "proposal_venue": ai_data.get("proposal_venue", ""),
            "proposal_participants": RichText(ai_data.get("proposal_participants", "")),
            "proposal_output": RichText(ai_data.get("proposal_output", "")),
            "pre_implementation": ai_data.get("pre_implementation", []),
            "implementation": ai_data.get("implementation", []),
            "post_implementation": ai_data.get("post_implementation", []),
            "funding": ai_data.get("funding", []),
            "total_amount": ai_data.get("total_amount", ""),
            "proposal_monitoring": RichText(ai_data.get("proposal_monitoring", "")),
            "endorsement_date": ai_data.get("endorsement_date", ""),
            "principal_name": ai_data.get("principal_name", ""),
            "principal_position": ai_data.get("principal_position", ""),
            "term_year": ai_data.get("term_year", ""),
            "first_name": first_name_db,
            "last_name": last_name_db,
            "position": position_db,
            "school_name": school_name
        }
    else: # DLL context
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

# Route the base URL directly to your Landing Page
@app.get("/")
def read_root():
    return RedirectResponse(url="/EduAssistAI_LandingPage.html")

# Serve all HTML, CSS, and JS files
app.mount("/", StaticFiles(directory=".", html=True), name="static")