from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, auth
import google.generativeai as genai
import os
import json
import re
from dotenv import load_dotenv
import datetime

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'she360-secret-key')
CORS(app)

# Initialize Firebase — fixed auth_uri and token_uri
cred = credentials.Certificate({
    "type": "service_account",
    "project_id": os.getenv('FIREBASE_PROJECT_ID'),
    "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
    "private_key": (os.getenv('FIREBASE_PRIVATE_KEY') or "").replace('\\n', '\n'),
    "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
    "client_id": os.getenv('FIREBASE_CLIENT_ID'),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_X509_CERT_URL')
})

firebase_admin.initialize_app(cred)
db = firestore.client()

# Initialize Gemini AI
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-1.5-flash')

CATEGORIES = ['finance', 'skincare', 'menstrual', 'sexual', 'mental', 'safety', 'self-defense']

# ── Health check ──────────────────────────────────────────────────────────────

@app.route('/healthz')
def healthz():
    return {"status": "ok"}

# ── Page routes ───────────────────────────────────────────────────────────────

@app.route('/')
def home():
    articles_ref = db.collection('articles')
    article_list = []
    for article in articles_ref.stream():
        data = article.to_dict()
        data['id'] = article.id
        article_list.append(data)
    return render_template('index.html', articles=article_list, categories=CATEGORIES)

@app.route('/login')
def login_page():
    firebase_web_config = {
        "apiKey": os.getenv('FIREBASE_WEB_API_KEY', ''),
        "authDomain": f"{os.getenv('FIREBASE_PROJECT_ID', '')}.firebaseapp.com",
        "projectId": os.getenv('FIREBASE_PROJECT_ID', ''),
    }
    return render_template('login.html', firebase_web_config=firebase_web_config)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    user_id = session['user_id']
    bookmarks_ref = db.collection('bookmarks').where('user_id', '==', user_id)
    bookmark_list = []
    for bookmark in bookmarks_ref.stream():
        data = bookmark.to_dict()
        data['id'] = bookmark.id
        bookmark_list.append(data)
    return render_template('dashboard.html', bookmarks=bookmark_list)

@app.route('/admin')
def admin():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    articles_ref = db.collection('articles')
    article_list = []
    for article in articles_ref.stream():
        data = article.to_dict()
        data['id'] = article.id
        article_list.append(data)
    return render_template('admin.html', articles=article_list, categories=CATEGORIES)

@app.route('/article/<article_id>')
def article_detail(article_id):
    doc = db.collection('articles').document(article_id).get()
    if not doc.exists:
        return redirect(url_for('home'))
    data = doc.to_dict()
    data['id'] = doc.id
    # Increment views
    db.collection('articles').document(article_id).update({'views': firestore.Increment(1)})
    return render_template('article.html', article=data, categories=CATEGORIES)

# ── Auth API ──────────────────────────────────────────────────────────────────

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.json
    try:
        user = auth.create_user(email=data['email'], password=data['password'])
        db.collection('users').document(user.uid).set({
            'email': data['email'],
            'name': data.get('name', ''),
            'created_at': firestore.SERVER_TIMESTAMP
        })
        return jsonify({'success': True, 'uid': user.uid})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    try:
        session['user_id'] = data['uid']
        return jsonify({'success': True})
    except Exception:
        return jsonify({'success': False}), 400

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'success': True})

# ── Articles API ──────────────────────────────────────────────────────────────

@app.route('/api/articles')
def get_articles():
    category = request.args.get('category', '')
    search = request.args.get('search', '').lower()
    query = db.collection('articles')
    if category:
        query = query.where('category', '==', category)
    article_list = []
    for article in query.stream():
        data = article.to_dict()
        data['id'] = article.id
        if search:
            title_match = search in (data.get('title', '')).lower()
            content_match = search in (data.get('content', '')[:200]).lower()
            if not title_match and not content_match:
                continue
        article_list.append(data)
    return jsonify(article_list)

@app.route('/api/generate-article', methods=['POST'])
def generate_article():
    data = request.json
    topic = data['topic']
    category = data['category']
    tone = data['tone']

    prompt = f"""
Generate a comprehensive article about "{topic}" for women in the {category} category.
Tone: {tone}

Return ONLY a valid JSON object (no markdown, no backticks) with this exact structure:
{{
  "title": "Catchy, compelling title",
  "category": "{category}",
  "introduction": "Engaging 2-3 sentence introduction",
  "content": "Full article body with ## subheadings, at least 800 words",
  "tips": ["Tip 1", "Tip 2", "Tip 3", "Tip 4", "Tip 5"],
  "conclusion": "Empowering 2-3 sentence conclusion"
}}
Make it educational, empowering, and focused on women's wellbeing.
"""
    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'^```\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {
                'title': topic.title(),
                'introduction': '',
                'content': raw,
                'tips': [],
                'conclusion': ''
            }

        article_data = {
            'title': parsed.get('title', topic.title()),
            'category': category,
            'topic': topic,
            'tone': tone,
            'introduction': parsed.get('introduction', ''),
            'content': parsed.get('content', ''),
            'tips': parsed.get('tips', []),
            'conclusion': parsed.get('conclusion', ''),
            'created_at': firestore.SERVER_TIMESTAMP,
            'views': 0
        }

        doc_ref = db.collection('articles').add(article_data)
        article_data['id'] = doc_ref[1].id
        return jsonify({'success': True, 'article': article_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/article/<article_id>', methods=['DELETE'])
def delete_article(article_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    try:
        db.collection('articles').document(article_id).delete()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ── Bookmarks API ─────────────────────────────────────────────────────────────

@app.route('/api/bookmark', methods=['POST'])
def bookmark_article():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    data = request.json
    # Prevent duplicate bookmarks
    existing = db.collection('bookmarks') \
        .where('user_id', '==', user_id) \
        .where('article_id', '==', data['article_id']) \
        .stream()
    if any(True for _ in existing):
        return jsonify({'success': False, 'error': 'Already bookmarked'}), 409
    db.collection('bookmarks').add({
        'user_id': user_id,
        'article_id': data['article_id'],
        'article_title': data['title'],
        'created_at': firestore.SERVER_TIMESTAMP
    })
    return jsonify({'success': True})

@app.route('/api/bookmark/<bookmark_id>', methods=['DELETE'])
def delete_bookmark(bookmark_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    db.collection('bookmarks').document(bookmark_id).delete()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True)
