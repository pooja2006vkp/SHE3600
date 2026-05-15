from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, auth
import google.generativeai as genai
import os
from dotenv import load_dotenv
import datetime

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'she360-secret-key')
CORS(app)

# Initialize Firebase
cred = credentials.Certificate({
    "type": "service_account",
    "project_id": os.getenv('FIREBASE_PROJECT_ID'),
    "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
    "private_key": (os.getenv('FIREBASE_PRIVATE_KEY') or "").replace('\\n', '\n'),
    "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
    "client_id": os.getenv('FIREBASE_CLIENT_ID'),
    "auth_uri": "https://oauth2.googleapis.com/token",
    "token_uri": "https://oauth2.googleapis.com/revoke",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_X509_CERT_URL')
})

firebase_admin.initialize_app(cred)
db = firestore.client()

# Initialize Gemini AI
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-1.5-flash')

# Categories
CATEGORIES = ['finance', 'skincare', 'menstrual', 'sexual', 'mental', 'safety', 'self-defense']

@app.route('/')
def home():
    # Get all articles
    articles_ref = db.collection('articles')
    articles = articles_ref.stream()
    article_list = []
    
    for article in articles:
        data = article.to_dict()
        data['id'] = article.id
        article_list.append(data)
    
    return render_template('index.html', articles=article_list, categories=CATEGORIES)

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    
    user_id = session['user_id']
    bookmarks_ref = db.collection('bookmarks').where('user_id', '==', user_id)
    bookmarks = bookmarks_ref.stream()
    bookmark_list = []
    
    for bookmark in bookmarks:
        data = bookmark.to_dict()
        data['id'] = bookmark.id
        bookmark_list.append(data)
    
    return render_template('dashboard.html', bookmarks=bookmark_list)

@app.route('/admin')
def admin():
    # Simple admin check (in production, use proper auth)
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    
    articles_ref = db.collection('articles')
    articles = articles_ref.stream()
    article_list = []
    
    for article in articles:
        data = article.to_dict()
        data['id'] = article.id
        article_list.append(data)
    
    return render_template('admin.html', articles=article_list, categories=CATEGORIES)

# API Routes
@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.json
    try:
        user = auth.create_user(
            email=data['email'],
            password=data['password']
        )
        # Create user profile
        db.collection('users').document(user.uid).set({
            'email': data['email'],
            'created_at': firestore.SERVER_TIMESTAMP
        })
        return jsonify({'success': True, 'uid': user.uid})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    try:
        # Verify password (Firebase handles this)
        session['user_id'] = data['uid']  # Frontend sends uid after Firebase auth
        return jsonify({'success': True})
    except:
        return jsonify({'success': False}), 400

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'success': True})

@app.route('/api/generate-article', methods=['POST'])
def generate_article():
    data = request.json
    topic = data['topic']
    category = data['category']
    tone = data['tone']
    
    # Create prompt for Gemini
    prompt = f"""
    Generate a comprehensive article about "{topic}" for women in the {category} category.
    Tone: {tone}
    
    Structure the response in JSON format with:
    {{
        "title": "Catchy title",
        "category": "{category}",
        "introduction": "200 word introduction",
        "content": "1500 word main content with subheadings",
        "tips": ["Tip 1", "Tip 2", "Tip 3", "Tip 4", "Tip 5"],
        "conclusion": "200 word conclusion"
    }}
    Make it educational, empowering, and feminine-focused.
    """
    
    try:
        response = model.generate_content(prompt)
        generated_text = response.text
        
        # Parse JSON response (simplified)
        lines = generated_text.split('\n')
        article_data = {
            'title': topic.title(),
            'category': category,
            'topic': topic,
            'tone': tone,
            'content': generated_text[:2000],  # Limit length
            'tips': [f"Tip {i+1}" for i in range(5)],
            'created_at': firestore.SERVER_TIMESTAMP,
            'views': 0
        }
        
        # Save to Firestore
        doc_ref = db.collection('articles').add(article_data)
        article_data['id'] = doc_ref[1].id
        
        return jsonify({'success': True, 'article': article_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bookmark', methods=['POST'])
def bookmark_article():
    data = request.json
    user_id = session.get('user_id')
    
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    bookmark_data = {
        'user_id': user_id,
        'article_id': data['article_id'],
        'article_title': data['title'],
        'created_at': firestore.SERVER_TIMESTAMP
    }
    
    db.collection('bookmarks').add(bookmark_data)
    return jsonify({'success': True})

@app.route('/api/articles')
def get_articles():
    category = request.args.get('category', '')
    search = request.args.get('search', '')
    
    query = db.collection('articles')
    if category:
        query = query.where('category', '==', category)
    
    articles = query.stream()
    article_list = []
    
    for article in articles:
        data = article.to_dict()
        data['id'] = article.id
        
        # Simple search
        if search and search.lower() not in data['title'].lower() and search.lower() not in data['content'][:100].lower():
            continue
            
        article_list.append(data)
    
    return jsonify(article_list)

if __name__ == '__main__':
    app.run(debug=True)