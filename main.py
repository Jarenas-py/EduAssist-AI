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
from fastapi import Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

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

class DocumentRequest(BaseModel):
    prompt: str
    template_type: Optional[str] = "dll" 
    api_key: str # <-- The backend now demands the key from the frontend

@app.post("/api/generate-dll")
async def generate_dll(req: DocumentRequest):
    if not req.api_key:
        print("❌ ERROR: API Key is missing from request!")
        raise HTTPException(status_code=400, detail="Gemini API Key is missing. Please provide your key.")
    
    # Configure Gemini using the end-user's provided key dynamically
    genai.configure(api_key=req.api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # Default fallback values for guest mode
    teacher_full_name = "Juan Dela Cruz"
    school_name = "Las Piñas National High School"
    first_name_db = "Juan"
    last_name_db = "Dela Cruz"
    position_db = "Teacher I"

    if req.template_type == "narrative":
        gemini_prompt = f"""
        You are an expert DepEd Philippines teacher assistant. 
        Based on this context: "{req.prompt}", generate a Narrative Report.
        
        You MUST respond with a raw JSON object containing EXACTLY these keys:
        "session_topic", "session_speaker", "date_time", "session_venue", "narrative_report",
        "teacher_name", "position".
        """
        template_file = "DEPED_docs/NarrativeReport_Template.docx"

    elif req.template_type == "proposal":
        gemini_prompt = f"""
        You are an expert DepEd Philippines teacher assistant. 
        Based on this context: "{req.prompt}", generate an Activity Proposal.
        
        You MUST respond with a raw JSON object containing EXACTLY these keys:
        "proposal_title", "proposal_rationale", "proposal_objectives", 
        "proposal_data", "proposal_beneficiaries", "proposal_output", 
        "teacher_name", "position", "total_amount",
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
        "lesson_title", "subject_name", "teacher_name", "grade_level", "teaching_week", "teaching_date",
        "references", "content_standards", "learning_objectives", 
        "learner_context", "prior_knowledge", "lesson_purpose", "lesson_development", "lesson_discussion", 
        "lesson_deepening", "lesson_application", "generalization", "lesson_materials", "learning_resources",
        "integration", "formative_assessment", "extended_learning", "reflection".

        CRITICAL INSTRUCTIONS: 
        1. EVERY value in your JSON MUST be a single String. 
        2. Do NOT return arrays or nested objects (e.g., do NOT use ["item 1", "item 2"]). 
        3. If a section requires a list (like learning objectives), return it as a single string with bullet points and use "\\n" for line breaks.
        4. Do not leave any key blank.
        """
        template_file = "DEPED_docs/DLL_Template.docx"
    
    try:
        print("⏳ Asking Gemini to generate document... (This may take 10-15 seconds)")
        response = model.generate_content(
            gemini_prompt,
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        
        clean_text = response.text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
            
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
            
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

    if req.template_type == "narrative":
        context = {
            "session_topic": ai_data.get("session_topic", ""),
            "session_speaker": ai_data.get("session_speaker", ""),
            "date_time": ai_data.get("date_time", ""),
            "session_venue": ai_data.get("session_venue", ""),
            "narrative_report": RichText(ai_data.get("narrative_report", "")),
            "position": ai_data.get("position", position_db),
            "teacher_name": ai_data.get("teacher_name", teacher_full_name),
        }
    elif req.template_type == "proposal":
        context = {
            "proposal_title": ai_data.get("proposal_title", ""),
            "proposal_rationale": RichText(ai_data.get("proposal_rationale", "")),
            "proposal_objectives": RichText(ai_data.get("proposal_objectives", "")),
            "proposal_data": ai_data.get("proposal_data", ""),
            "proposal_beneficiaries": RichText(ai_data.get("proposal_beneficiaries", "")),
            "proposal_output": RichText(ai_data.get("proposal_output", "")),
            "teacher_name": ai_data.get("teacher_name", teacher_full_name),
            "position": ai_data.get("position", position_db),
            "total_amount": ai_data.get("total_amount", ""),
            "pre_implementation": ai_data.get("pre_implementation", []),
            "implementation": ai_data.get("implementation", []),
            "post_implementation": ai_data.get("post_implementation", []),
            "funding": ai_data.get("funding", []),
            "school_name": school_name
        }
    else: # DLL context
        context = {
            "lesson_title": ai_data.get("lesson_title", ""),
            "subject_name": ai_data.get("subject_name", ""),
            "grade_level": ai_data.get("grade_level", ""),
            "teaching_week": ai_data.get("teaching_week", ""),
            "teaching_date": ai_data.get("teaching_date", ""),
            "references": RichText(ai_data.get("references", "")),
            "content_standards": RichText(ai_data.get("content_standards", "")),
            "learning_objectives": RichText(ai_data.get("learning_objectives", "")),
            "learner_context": RichText(ai_data.get("learner_context", "")),
            "prior_knowledge": RichText(ai_data.get("prior_knowledge", "")),
            "lesson_purpose": RichText(ai_data.get("lesson_purpose", "")),
            "lesson_development": RichText(ai_data.get("lesson_development", "")),
            "lesson_discussion": RichText(ai_data.get("lesson_discussion", "")),
            "lesson_deepening": RichText(ai_data.get("lesson_deepening", "")),
            "lesson_application": RichText(ai_data.get("lesson_application", "")),
            "generalization": RichText(ai_data.get("generalization", "")),
            "lesson_materials": RichText(ai_data.get("lesson_materials", "")),
            "learning_resources": RichText(ai_data.get("learning_resources", "")),
            "integration": RichText(ai_data.get("integration", "")),
            "formative_assessment": RichText(ai_data.get("formative_assessment", "")),
            "extended_learning": RichText(ai_data.get("extended_learning", "")),
            "reflection": RichText(ai_data.get("reflection", "")),
            "teacher_name": ai_data.get("teacher_name", teacher_full_name), # <-- FIXED
            "school_name": ai_data.get("school_name", school_name)
        }

    doc.render(context)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    doc.save(temp_file.name)
    print("🎉 Document successfully generated! Sending to browser...")

    return FileResponse(
        path=temp_file.name, 
        filename="EduAssist_Generated_Document.docx", 
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    
# Route the base URL directly to your Landing Page
@app.get("/")
def read_root():
    return RedirectResponse(url="/EduAssistAI_LandingPage.html")

# Serve all HTML, CSS, and JS files
app.mount("/", StaticFiles(directory=".", html=True), name="static")