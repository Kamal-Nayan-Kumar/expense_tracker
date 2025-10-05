# 🤖 AI Expense Tracker Telegram Bot

This project provides a seamless way to track personal expenses via Telegram. It uses the multimodal power of **Gemini 2.5 Flash** for highly accurate data extraction and a **Vercel** serverless backend with **Appwrite** for persistence.

## ✨ Key Features

* **Intelligent Logging:** Upload a **photo of a receipt** or type the expense in **natural language**.
* **AI Extraction:** Gemini extracts `Category`, `Description`, and `Amount` and converts it to a clean JSON object.
* **Structured Storage:** Data is saved to your self-hosted or cloud **Appwrite** database.
* **Real-time Reports:** Use slash commands to instantly summarize spending totals by day, week, or month.
* **Stack:** Python/FastAPI backend on Vercel.

---

## 👤 Bot User Guide (End-User)

Start a conversation with the bot on Telegram and use the following:

### 1. Logging an Expense

| Method | Example Input | Expected Output |
| :--- | :--- | :--- |
| **Image/Receipt** | Upload an image of a bill (photo or document). | `✅ Expense Saved! Category: Food, Amount: ₹450.00` |
| **Natural Language** | `Paid 220 for pizza at Pizza Hut` | `✅ Expense Saved! Category: Food, Amount: ₹220.00` |

### 2. Reports

Use the command menu (visible when typing `/`) for instant summaries:

| Command | Function |
| :--- | :--- |
| `/daily` | Shows total expenses and category breakdown for **Today**. |
| `/week` | Shows total expenses and category breakdown for the **Current Week**. |
| `/month` | Shows total expenses and category breakdown for the **Current Month**.

---
👉 If you want to give a try:
* **Telegram Bot Username:** [Bot Link](https://t.me/expense_tracker_nayan90k_bot)
---

## 💻 Developer Setup Guide (Self-Hosting)

### 1. Prerequisites & Credentials

You need the following accounts and credentials:

* **Telegram Bot Token:** From [@BotFather](https://t.me/BotFather).
* **Gemini API Key:** From Google AI Studio.
* **Appwrite:** Project ID, Endpoint (`https://cloud.appwrite.io/v1`), and an API Key (with Database R/W permissions).
* **Vercel:** Account linked to your Git repository.

### 2. Appwrite Database Configuration

Create one Collection in your Appwrite Database (`<APPWRITE_DATABASE_ID>`) named `expenses` (`<APPWRITE_COLLECTION_ID>`) with the following attributes:

| Attribute Key | Type | Required | Indexing |
| :--- | :--- | :--- | :--- |
| `telegram_user_id` | Integer | Yes | **Index (Required)** |
| `category` | String | Yes | Index |
| `description` | String | Yes | |
| `amount` | Float | Yes | |
| `created_at` | DateTime | Yes | **Datetime Index (Crucial for reports)** |

### 3. Project Structure & Dependencies

Your repository must follow this structure for Vercel deployment:

```
/project-root
├── api/
│   └── index.py      \# FastAPI application (main logic)
├── requirements.txt
└── vercel.json
```


**`requirements.txt`**

```
fastapi
uvicorn
appwrite
google-genai
requests
pydantic
````

**`vercel.json`**
```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/index.py"
    }
  ]
}
````

### 4\. Vercel Deployment

1.  **Environment Variables:** Go to your Vercel Project Settings and add the following Environment Variables. These must match the keys in your Python code:

      * `TELEGRAM_BOT_TOKEN`
      * `GEMINI_API_KEY`
      * `APPWRITE_ENDPOINT`
      * `APPWRITE_PROJECT_ID`
      * `APPWRITE_API_KEY`
      * `APPWRITE_DATABASE_ID`
      * `APPWRITE_COLLECTION_ID`

2.  **Deploy:** Deploy your project via the Vercel website dashboard by linking your Git repository.

### 5\. Set the Telegram Webhook

Once the Vercel deployment is live (e.g., at `https://your-app.vercel.app/`), run this **single command** in your terminal (replace placeholders with your actual values):

```bash
curl -F "url=https://<YOUR_VERCEL_URL>" "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook"
```

A success response (`"ok":true`) confirms Telegram is routing messages to your Vercel backend.
