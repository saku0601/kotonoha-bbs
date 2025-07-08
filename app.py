import os
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, User, Post, Comment, File
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

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

# アップロード設定
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'xlsx', 'mp4', 'mov', 'avi', 'webm'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                new_file = File(filename=filename, mimetype=mimetype, post_id=new_post.id)
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
    post = Post.query.get_or_404(post_id)
    # 投稿者または管理者のみ許可
    if post.user_id != current_user.id and not current_user.is_admin:
        flash('自分の投稿または管理者のみ画像を追加できます。')
        return redirect(url_for('board'))
    file = request.files.get('new_image')
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        mimetype = file.mimetype
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        new_file = File(filename=filename, mimetype=mimetype, post_id=post.id)
        db.session.add(new_file)
        db.session.commit()
        flash('画像を追加しました。')
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
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.session.delete(file)
    db.session.commit()
    flash('画像を削除しました。')
    return redirect(url_for('board'))

if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DATABASE_URL"):
    # Railwayや本番環境でのみ実行（ローカル開発時は不要なら条件を調整）
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', password=generate_password_hash('adminpass'), is_admin=True)
            db.session.add(admin)
            db.session.commit()
            print('管理者ユーザーadminを作成しました')
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)