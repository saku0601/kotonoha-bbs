import os
import json
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, User, Post, Comment, File
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import firebase_admin
from firebase_admin import credentials, storage

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# Heroku環境ではDATABASE_URLを使う
if 'DATABASE_URL' in os.environ:
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL'].replace('postgres://', 'postgresql://')
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'corkboard.sqlite')}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Firebase設定
def init_firebase():
    try:
        # 環境変数からFirebase設定を読み込み
        service_account = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
        storage_bucket = os.environ.get('FIREBASE_STORAGE_BUCKET', 'kotonoha-bbs.firebasestorage.app')
        
        print(f"Firebase初期化開始:")
        print(f"  - FIREBASE_SERVICE_ACCOUNT: {'設定済み' if service_account else '未設定'}")
        print(f"  - FIREBASE_STORAGE_BUCKET: {storage_bucket}")
        
        if service_account:
            # サービスアカウントキーをJSONとして解析
            service_account_info = json.loads(service_account)
            
            # Firebase Admin SDKを初期化
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred, {
                'storageBucket': storage_bucket
            })
            print("Firebase初期化成功")
            return True
        else:
            print("FIREBASE_SERVICE_ACCOUNT環境変数が設定されていません")
            return False
    except Exception as e:
        print(f"Firebase初期化エラー: {e}")
        print(f"エラーの詳細: {type(e).__name__}")
        return False

# Firebase初期化
firebase_initialized = init_firebase()

# アプリケーション初期化
def init_app():
    with app.app_context():
        try:
            # 既存のテーブル構造を確認
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            # fileテーブルが存在する場合、urlカラムの存在を確認
            if 'file' in existing_tables:
                columns = [col['name'] for col in inspector.get_columns('file')]
                if 'url' not in columns:
                    print("fileテーブルにurlカラムが存在しません。ALTER TABLEで追加します。")
                    # データを保持したままurlカラムを追加
                    db.engine.execute('ALTER TABLE file ADD COLUMN url VARCHAR(500)')
                    print("urlカラムを追加しました")
                    
                    # 既存のファイルレコードにURLを設定
                    try:
                        files = File.query.all()
                        for file in files:
                            if not file.url:
                                # ローカルファイルのURLを生成
                                file.url = url_for('uploaded_file', filename=file.filename, _external=True)
                        db.session.commit()
                        print(f"{len(files)}個のファイルレコードにURLを設定しました")
                    except Exception as e:
                        print(f"既存ファイルのURL設定エラー: {e}")
                    
                    # uploadsフォルダのファイルをチェックして、DBレコードがないものを追加
                    try:
                        import os
                        upload_dir = app.config['UPLOAD_FOLDER']
                        if os.path.exists(upload_dir):
                            for filename in os.listdir(upload_dir):
                                file_path = os.path.join(upload_dir, filename)
                                if os.path.isfile(file_path):
                                    # このファイルのDBレコードが存在するかチェック
                                    existing_file = File.query.filter_by(filename=filename).first()
                                    if not existing_file:
                                        # MIMEタイプを推測
                                        import mimetypes
                                        mimetype, _ = mimetypes.guess_type(filename)
                                        if not mimetype:
                                            mimetype = 'application/octet-stream'
                                        
                                        # 新しいファイルレコードを作成
                                        new_file = File(
                                            filename=filename,
                                            mimetype=mimetype,
                                            url=url_for('uploaded_file', filename=filename, _external=True),
                                            post_id=1  # 仮の投稿ID（後で修正が必要）
                                        )
                                        db.session.add(new_file)
                                        print(f"ファイルレコードを追加: {filename}")
                            
                            db.session.commit()
                            print("uploadsフォルダのファイルをDBに再登録しました")
                    except Exception as e:
                        print(f"uploadsフォルダのファイル再登録エラー: {e}")
                else:
                    print("データベーステーブルは正常です")
            else:
                db.create_all()
                print("データベーステーブルを作成しました")
            
            # 管理者ユーザーが存在しない場合は作成
            if not User.query.filter_by(username='admin').first():
                admin_user = User(username='admin', password=generate_password_hash('admin'), is_admin=True)
                db.session.add(admin_user)
                db.session.commit()
                print("管理者ユーザーを作成しました: admin/admin")
                
        except Exception as e:
            print(f"データベース初期化エラー: {e}")
            # エラーが発生した場合のみ強制的に再作成
            try:
                print("エラーによりデータベースを強制再作成しました")
                db.drop_all()
                db.create_all()
                
                # 管理者ユーザーを作成
                admin_user = User(username='admin', password=generate_password_hash('admin'), is_admin=True)
                db.session.add(admin_user)
                db.session.commit()
                print("管理者ユーザーを作成しました: admin/admin")
            except Exception as e2:
                print(f"強制再作成でもエラー: {e2}")

# 初期化実行
init_app()

# アップロード設定（ローカル用のフォールバック）
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'xlsx', 'mp4', 'mov', 'avi', 'webm'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_firebase(file, filename):
    """Firebase Storageにファイルをアップロード"""
    if not firebase_initialized:
        print("Firebaseが初期化されていないため、ローカル保存にフォールバックします")
        return None
    
    try:
        bucket = storage.bucket()
        blob = bucket.blob(f"uploads/{filename}")
        blob.upload_from_file(file)
        blob.make_public()
        return blob.public_url
    except Exception as e:
        print(f"Firebaseアップロードエラー: {e}")
        return None

def save_file_locally(file, filename):
    """ローカルにファイルを保存（フォールバック）"""
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)
    # ローカルファイルのURLを生成
    return url_for('uploaded_file', filename=filename, _external=True)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def index():
    return f'''
    ようこそ、{current_user.username}さん！<br>
    <a href="{url_for('board')}">コルクボードへ</a>
    '''

@app.route('/register', methods=['GET', 'POST'])
def register():
    flash('新規登録は管理者のみ可能です。')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('board'))
        flash('ユーザー名またはパスワードが間違っています。')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/post', methods=['GET', 'POST'])
@login_required
def post():
    if request.method == 'POST':
        content = request.form['content']
        files = request.files.getlist('files')
        if not content.strip() and not files:
            flash('内容またはファイルを入力してください。')
            return redirect(url_for('post'))
        new_post = Post(content=content, user_id=current_user.id)
        db.session.add(new_post)
        db.session.commit()
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                mimetype = file.mimetype
                # ローカルに保存またはFirebaseにアップロード
                file_url = upload_to_firebase(file, filename) or save_file_locally(file, filename)
                if file_url:
                    new_file = File(filename=filename, mimetype=mimetype, post_id=new_post.id, url=file_url)
                    db.session.add(new_file)
        db.session.commit()
        flash('付箋を投稿しました！')
        return redirect(url_for('board'))
    return render_template('post.html')

@app.route('/board')
@login_required
def board():
    q = request.args.get('q', '')
    if q:
        posts = Post.query.filter(Post.content.contains(q)).order_by(Post.id.desc()).all()
    else:
        posts = Post.query.order_by(Post.id.desc()).all()
    comments = Comment.query.all()
    # ユーザーID→ユーザー名の辞書を作成
    user_dict = {user.id: user.username for user in User.query.all()}
    return render_template('board.html', posts=posts, comments=comments, user_dict=user_dict)

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def comment(post_id):
    content = request.form['comment']
    if not content.strip():
        flash('コメントを入力してください。')
        return redirect(url_for('board'))
    new_comment = Comment(content=content, user_id=current_user.id, post_id=post_id)
    db.session.add(new_comment)
    db.session.commit()
    flash('コメントを投稿しました！')
    return redirect(url_for('board'))

@app.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id and not current_user.is_admin:
        flash('自分の投稿または管理者のみ編集できます。')
        return redirect(url_for('board'))
    if request.method == 'POST':
        post.content = request.form['content']
        db.session.commit()
        flash('投稿を編集しました。')
        return redirect(url_for('board'))
    return render_template('edit_post.html', post=post)

@app.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id and not current_user.is_admin:
        flash('自分の投稿または管理者のみ削除できます。')
        return redirect(url_for('board'))
    # 画像ファイルも削除（例外処理付きで安全に）
    files = getattr(post, 'files', [])
    for file in files:
        try:
            # ファイルがFirebaseかローカルかによって処理を分岐
            if file.url and file.url.startswith('https://firebasestorage.googleapis.com/v0/b/'):
                # Firebaseから削除
                if firebase_initialized:
                    try:
                        bucket = storage.bucket()
                        blob = bucket.blob(f"uploads/{file.filename}")
                        blob.delete()
                    except Exception as e:
                        print(f"Firebase削除エラー: {e}")
                else:
                    print("Firebaseが初期化されていないため、Firebaseからの削除をスキップします")
            else:
                # ローカルから削除
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
            db.session.delete(file)
        except Exception as e:
            print(f"ファイル削除エラー: {e}")
    db.session.delete(post)
    db.session.commit()
    flash('投稿を削除しました。')
    return redirect(url_for('board'))

@app.route('/edit_comment/<int:comment_id>', methods=['POST'])
@login_required
def edit_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id:
        flash('自分のコメントのみ編集できます。')
        return redirect(url_for('board'))
    new_content = request.form['content']
    if not new_content.strip():
        flash('コメント内容を入力してください。')
        return redirect(url_for('board'))
    comment.content = new_content
    db.session.commit()
    flash('コメントを編集しました。')
    return redirect(url_for('board'))

@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id:
        flash('自分のコメントのみ削除できます。')
        return redirect(url_for('board'))
    db.session.delete(comment)
    db.session.commit()
    flash('コメントを削除しました。')
    return redirect(url_for('board'))

@app.route('/admin/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    if not current_user.is_admin:
        flash('管理者のみアクセス可能です。')
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('そのユーザー名は既に使われています。')
            return redirect(url_for('add_user'))
        new_user = User(username=username, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        flash('ユーザーを追加しました。')
        return redirect(url_for('add_user'))
    return render_template('add_user.html')

@app.route('/edit_post/<int:post_id>/add_image', methods=['POST'])
@login_required
def add_image(post_id):
    print("add_image called", post_id)
    post = Post.query.get_or_404(post_id)
    # 投稿者または管理者のみ許可
    if post.user_id != current_user.id and not current_user.is_admin:
        flash('自分の投稿または管理者のみ画像を追加できます。')
        return redirect(url_for('board'))
    file = request.files.get('new_image')
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        mimetype = file.mimetype
        # ローカルに保存またはFirebaseにアップロード
        file_url = upload_to_firebase(file, filename) or save_file_locally(file, filename)
        if file_url:
            new_file = File(filename=filename, mimetype=mimetype, post_id=post.id, url=file_url)
            db.session.add(new_file)
            db.session.commit()
            print("file saved:", filename)
            print("Fileレコード追加:", new_file)
            flash('画像を追加しました。')
        else:
            flash('画像のアップロードに失敗しました。')
    else:
        flash('有効な画像ファイルを選択してください。')
    return redirect(url_for('board'))

@app.route('/edit_post/<int:post_id>/delete_image/<int:file_id>', methods=['POST'])
@login_required
def delete_image(post_id, file_id):
    post = Post.query.get_or_404(post_id)
    file = File.query.get_or_404(file_id)
    # 投稿者または管理者のみ許可
    if post.user_id != current_user.id and not current_user.is_admin:
        flash('自分の投稿または管理者のみ画像を削除できます。')
        return redirect(url_for('board'))
    # ファイルが該当投稿に紐づいているか確認
    if file.post_id != post.id:
        flash('この画像はこの投稿に紐づいていません。')
        return redirect(url_for('board'))
    # サーバー上のファイルも削除
    if file.url and file.url.startswith('https://firebasestorage.googleapis.com/v0/b/'):
        # Firebaseから削除
        if firebase_initialized:
            try:
                bucket = storage.bucket()
                blob = bucket.blob(f"uploads/{file.filename}")
                blob.delete()
            except Exception as e:
                print(f"Firebase削除エラー: {e}")
        else:
            print("Firebaseが初期化されていないため、Firebaseからの削除をスキップします")
    else:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    db.session.delete(file)
    db.session.commit()
    flash('画像を削除しました。')
    return redirect(url_for('board'))

@app.route('/api/post/<int:post_id>/images')
@login_required
def get_post_images(post_id):
    post = Post.query.get_or_404(post_id)
    images = []
    for file in post.files:
        if file.mimetype and file.mimetype.startswith('image/'):
            # URLの生成を改善
            if file.url:
                file_url = file.url
            else:
                # ローカルファイルの場合、絶対URLを生成
                file_url = request.host_url.rstrip('/') + url_for('uploaded_file', filename=file.filename)
            
            images.append({
                'id': file.id,
                'filename': file.filename,
                'url': file_url
            })
    return jsonify({'images': images})

@app.route('/api/post/<int:post_id>/detail')
@login_required
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    user = User.query.get(post.user_id)
    files = []
    for file in post.files:
        # URLの生成を改善
        if file.url:
            file_url = file.url
        else:
            # ローカルファイルの場合、絶対URLを生成
            file_url = request.host_url.rstrip('/') + url_for('uploaded_file', filename=file.filename)
        
        files.append({
            'filename': file.filename,
            'mimetype': file.mimetype or '',
            'url': file_url
        })
        print(f"File: {file.filename}, URL: {file_url}, MIME: {file.mimetype}")
    
    result = {
        'id': post.id,
        'user': user.username if user else '不明',
        'content': post.content,
        'files': files
    }
    print(f"API Response: {result}")
    return jsonify(result)

@app.route('/admin/files')
@login_required
def admin_files():
    if not current_user.is_admin:
        flash('管理者のみアクセス可能です')
        return redirect(url_for('board'))
    
    import os
    files = []
    upload_dir = app.config['UPLOAD_FOLDER']
    
    # データベースのファイルレコードも取得
    db_files = File.query.all()
    db_file_dict = {f.filename: f for f in db_files}
    
    # Firebase Storageの状況確認
    firebase_status = "未初期化"
    if firebase_initialized:
        try:
            bucket = storage.bucket()
            firebase_status = f"初期化済み (Bucket: {bucket.name})"
        except Exception as e:
            firebase_status = f"エラー: {e}"
    else:
        firebase_status = "Firebase初期化失敗"
    
    if os.path.exists(upload_dir):
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            if os.path.isfile(file_path):
                # ファイルサイズをMB単位で表示
                size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
                db_file = db_file_dict.get(filename)
                files.append({
                    'name': filename,
                    'size_mb': size_mb,
                    'url': url_for('uploaded_file', filename=filename, _external=True),
                    'db_url': db_file.url if db_file else 'DBレコードなし',
                    'mimetype': db_file.mimetype if db_file else '不明',
                    'exists': True
                })
    else:
        flash('uploadsフォルダが存在しません')
    
    # DBレコードのみでファイルが存在しないものも表示
    for db_file in db_files:
        if not any(f['name'] == db_file.filename for f in files):
            files.append({
                'name': db_file.filename,
                'size_mb': 0,
                'url': 'ファイルなし',
                'db_url': db_file.url or 'URLなし',
                'mimetype': db_file.mimetype or '不明',
                'exists': False
            })
    
    return render_template('admin_files.html', files=files, firebase_status=firebase_status)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # 管理者ユーザーが存在しない場合は作成
        if not User.query.filter_by(username='admin').first():
            admin_user = User(username='admin', password=generate_password_hash('admin'), is_admin=True)
            db.session.add(admin_user)
            db.session.commit()
            print("管理者ユーザーを作成しました: admin/admin")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)