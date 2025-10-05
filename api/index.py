import os
import json
import logging
from datetime import datetime, timedelta
from io import BytesIO

import requests
from fastapi import FastAPI, Request, HTTPException
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from appwrite.id import ID
from google import genai
from google.genai import types

# --- 1. CONFIGURATION & CLIENT INITIALIZATION ---
# Load environment variables (will be loaded automatically by Vercel)
# Replace placeholders with your actual keys and IDs
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
APPWRITE_ENDPOINT = os.environ.get("APPWRITE_ENDPOINT")
APPWRITE_PROJECT_ID = os.environ.get("APPWRITE_PROJECT_ID")
APPWRITE_API_KEY = os.environ.get("APPWRITE_API_KEY")
APPWRITE_DATABASE_ID = os.environ.get("APPWRITE_DATABASE_ID") # e.g., 'default'
APPWRITE_COLLECTION_ID = os.environ.get("APPWRITE_COLLECTION_ID") # e.g., 'expenses'

# --- NEW CONSTANTS FOR LIMITS ---
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024 # 5 MB
MAX_TEXT_CHARS = 500

# Initialize Appwrite Client
appwrite_client = Client()
appwrite_client.set_endpoint(APPWRITE_ENDPOINT)
appwrite_client.set_project(APPWRITE_PROJECT_ID)
appwrite_client.set_key(APPWRITE_API_KEY)
appwrite_db = Databases(appwrite_client)

# Initialize Gemini Client
genai_client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = 'gemini-2.5-flash-lite'
SYSTEM_INSTRUCTION = """
You are an expert expense tracker API. Your sole function is to extract details from the provided image or text and return a single, valid JSON object.
RULES:
1. Category MUST be one of: 'Food', 'Travel', 'Study', 'Shopping', 'Utility', 'Subscription', 'Other'. 
2. Amount MUST be a string containing ONLY the total numerical value in INR (e.g., "150.75"). Do NOT include the currency symbol. Always find the final TOTAL.
3. Description should be a brief, one-line summary.
4. If extraction fails, return: {"Category": "ERROR", "Description": "Failed to process input.", "Amount": "0.00"}
"""

# Telegram API base URL for file download
TELEGRAM_FILE_URL = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

app = FastAPI()

# --- 2. CORE HELPER FUNCTIONS ---

def send_telegram_message(chat_id: int, text: str):
    """Sends a text message back to the Telegram user."""
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", data=payload)

def download_telegram_file(file_id: str) -> BytesIO:
    """Gets the file path and downloads the image bytes."""
    # 1. Get file_path from Telegram
    file_info_url = f"{TELEGRAM_API_URL}/getFile?file_id={file_id}"
    response = requests.get(file_info_url).json()
    file_path = response['result']['file_path']
    
    # 2. Download file bytes
    download_url = f"{TELEGRAM_FILE_URL}/{file_path}"
    file_response = requests.get(download_url)
    file_response.raise_for_status() # Raise exception for bad status codes
    
    return BytesIO(file_response.content)

def extract_expense_details(parts: list[types.Part]) -> dict:
    """Calls the Gemini API to extract structured data."""
    
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "Category": types.Schema(type=types.Type.STRING),
                "Description": types.Schema(type=types.Type.STRING),
                "Amount": types.Schema(type=types.Type.STRING) # Keep as string for Appwrite float conversion
            }
        )
    )

    response = genai_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=parts,
        config=config
    )
    
    return json.loads(response.text)

def get_query_time_range(command: str) -> tuple[datetime, datetime]:
    """Calculates the start and end dates for report commands."""
    today = datetime.now().date()
    
    if command == '/daily':
        start_date = datetime.combine(today, datetime.min.time())
        end_date = datetime.combine(today, datetime.max.time())
    elif command == '/week':
        # Start of the week (Monday)
        start_date = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
        end_date = datetime.combine(today, datetime.max.time())
    elif command == '/month':
        # Start of the current month
        start_date = datetime.combine(today.replace(day=1), datetime.min.time())
        end_date = datetime.combine(today, datetime.max.time())
    else:
        # Default to /daily if unknown
        start_date, end_date = get_query_time_range('/daily') 
        
    # Appwrite requires ISO 8601 format (including 'Z' for UTC if not using a specific timezone)
    return start_date.isoformat() + 'Z', end_date.isoformat() + 'Z'

# --- 3. TELEGRAM WEBHOOK HANDLER ---

# ADD THIS NEW FUNCTION:
@app.get("/")
def health_check():
    """Simple GET endpoint for Vercel health check."""
    return {"status": "Service is running", "message": "Listening for POST requests from Telegram..."}


@app.post("/")
async def handle_telegram_webhook(request: Request):
    """Main entry point for the Telegram Webhook."""
    try:
        update = await request.json()
        
        # We only care about messages
        if 'message' not in update:
            return {"status": "ok"} 

        message = update['message']
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        current_time = datetime.now().isoformat() + 'Z'
        
        # A. HANDLE COMMANDS (/daily, /week, /month)
        if 'text' in message and message['text'].startswith('/'):
            command = message['text'].lower()
            if command == '/start':
                welcome_message = (
                    "👋 *Welcome to your AI Expense Tracker!* 📊\n\n"
                    "I help you track your spending effortlessly.\n\n"
                    "**1. Record an Expense:**\n"
                    "   - 📸 **Upload** any photo of a bill or receipt.\n"
                    "   - 💬 **Type** in natural language (e.g., `220 pizza`, `paid 1500 for flight ticket`).\n\n"
                    "**2. Get Reports (Use the menu or type):**\n"
                    "   - /daily: See today's spending.\n"
                    "   - /week: See this week's spending.\n"
                    "   - /month: See this month's spending.\n\n"
                )
                send_telegram_message(chat_id, welcome_message)
                return {"status": "ok"}
            elif command in ['/daily', '/week', '/month']:
                return await generate_report(chat_id, user_id, command)
        
        
        # B. HANDLE EXPENSE INPUT (Photo, Document, or Text)
        
        gemini_parts = []
        file_id = None
        caption_text = None

        if 'photo' in message:
            # Get the highest resolution photo (last item in array)
            photo_data = message['photo'][-1]
            
            # --- FILE SIZE CHECK (PHOTO) ---
            if photo_data.get('file_size', 0) > MAX_FILE_SIZE_BYTES:
                send_telegram_message(chat_id, f"❌ *File Too Large!* The uploaded file size ({photo_data.get('file_size', 0) / 1024 / 1024:.2f} MB) exceeds the limit of {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} MB. Please send a smaller file.")
                return {"status": "ok"}
            
            file_id = photo_data['file_id']
            caption_text = message.get('caption')
            
        elif 'document' in message:
            # Handle image sent as a document
            doc_data = message['document']
            
            # --- FILE SIZE CHECK (DOCUMENT) ---
            if doc_data.get('file_size', 0) > MAX_FILE_SIZE_BYTES:
                send_telegram_message(chat_id, f"❌ *File Too Large!* The uploaded file size ({doc_data.get('file_size', 0) / 1024 / 1024:.2f} MB) exceeds the limit of {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} MB. Please send a smaller file.")
                return {"status": "ok"}
            
            file_id = doc_data['file_id']
            caption_text = message.get('caption')
            
        elif 'text' in message:
            # --- TEXT SIZE CHECK ---
            text_input = message['text']
            if len(text_input) > MAX_TEXT_CHARS:
                send_telegram_message(chat_id, f"❌ *Text Too Long!* Your input has {len(text_input)} characters, exceeding the limit of {MAX_TEXT_CHARS}. Please summarize your expense details.")
                return {"status": "ok"}
                
            # Natural language input (proceed if size is fine)
            gemini_parts.append(text_input)
            
        else:
            send_telegram_message(chat_id, "*Input Error*: Please send a bill image or write your expense (e.g., '150 food pizza').")
            return {"status": "ok"}
            
        # If a file was found (photo or document), prepare the Gemini parts
        if file_id:
            try:
                image_bytes = download_telegram_file(file_id)
                gemini_parts.append(types.Part.from_bytes(data=image_bytes.read(), mime_type='image/jpeg'))
                
                # Use caption or default text
                if caption_text:
                    # --- CAPTION SIZE CHECK (if photo/document has a caption) ---
                    if len(caption_text) > MAX_TEXT_CHARS:
                        send_telegram_message(chat_id, f"❌ *Caption Too Long!* Your caption has {len(caption_text)} characters, exceeding the limit of {MAX_TEXT_CHARS}. Please shorten your description.")
                        return {"status": "ok"}
                        
                    gemini_parts.append(caption_text)
                else:
                    gemini_parts.append("Extract expense details from this bill/receipt image.")
            except Exception as e:
                send_telegram_message(chat_id, f"⚠️ *File Download Error*: Could not retrieve file from Telegram. Check Vercel logs. Details: {str(e)}")
                return {"status": "ok"}
            
        # 1. Extract JSON using Gemini
        extracted_data = extract_expense_details(gemini_parts)
        
        if extracted_data.get('Category') == 'ERROR':
            send_telegram_message(chat_id, f"*Extraction Failed!* 😭 \n_Details_: {extracted_data.get('Description', 'N/A')}")
            return {"status": "ok"}
            
        # 2. Clean and Save to Appwrite
        expense_data = {
            "telegram_user_id": user_id,
            "category": extracted_data['Category'],
            "description": extracted_data['Description'],
            "amount": float(extracted_data['Amount']),
            "created_at": current_time,
        }
        
        appwrite_db.create_document(
            database_id=APPWRITE_DATABASE_ID,
            collection_id=APPWRITE_COLLECTION_ID,
            document_id=ID.unique(),
            data=expense_data,
            permissions=['read("user:' + str(user_id) + '")', 'write("user:' + str(user_id) + '")']
        )
        
        # 3. Send Confirmation
        response_text = (
            f"✅ *Expense Saved!* \n\n"
            f"*Category*: `{expense_data['category']}`\n"
            f"*Amount*: ₹`{expense_data['amount']:.2f}`\n"
            f"*Description*: `{expense_data['description']}`\n\n"
        )
        send_telegram_message(chat_id, response_text)

    except Exception as e:
        error_msg = f"An unexpected error occurred: {type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        # Always return 'ok' to Telegram to prevent it from retrying the webhook
        return {"status": "error", "message": error_msg}

    return {"status": "ok"}

# --- 4. REPORT GENERATION HANDLER ---

async def generate_report(chat_id: int, user_id: int, command: str):
    """Fetches and summarizes expenses for a given time period."""
    
    start_time, end_time = get_query_time_range(command)
    time_period = command[1:].capitalize()
    
    # Appwrite Query for documents in the time range and for the specific user
    queries = [
        Query.equal("telegram_user_id", user_id),
        Query.greater_than_equal("created_at", start_time),
        Query.less_than_equal("created_at", end_time),
        Query.limit(20) # Limit the results for safety
    ]
    
    try:
        results = appwrite_db.list_documents(
            database_id=APPWRITE_DATABASE_ID,
            collection_id=APPWRITE_COLLECTION_ID,
            queries=queries
        )
        
        expenses = results['documents']
        
        if not expenses:
            send_telegram_message(chat_id, f"😔 No expenses found for the *{time_period}* period.")
            return {"status": "ok"}
        
        # Calculate totals and category distribution
        total_spent = 0.0
        category_totals = {}
        
        for exp in expenses:
            amount = exp['amount']
            category = exp['category']
            total_spent += amount
            category_totals[category] = category_totals.get(category, 0.0) + amount
            
        # Format report message
        report_text = f"📊 *{time_period} Expense Report* 📊\n"
        report_text += f"Total Expenses: ₹`{total_spent:.2f}`\n\n"
        report_text += "*Category Breakdown:*\n"
        
        for category, total in sorted(category_totals.items(), key=lambda item: item[1], reverse=True):
            percentage = (total / total_spent) * 100
            report_text += f" • {category}: ₹`{total:.2f}` (`{percentage:.1f}`%)\n"
            
        send_telegram_message(chat_id, report_text)

    except Exception as e:
        send_telegram_message(chat_id, f"⚠️ *Report Error*: Failed to fetch data from Appwrite. Details: {str(e)}")
        
    return {"status": "ok"}