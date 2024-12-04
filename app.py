from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text  # 匯入 text 函數
import os

app = Flask(__name__)

# 配置資料庫，使用 SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'

# 新增上傳圖片的路徑設定
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制最大上傳大小為16MB

# 初始化資料庫
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# 定義 User 模型
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)  # 顯示名稱
    password = db.Column(db.String(150), nullable=False)

# 定義 Post 模型
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(150), nullable=True)  # 新增圖片路徑欄位
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', backref=db.backref('posts', lazy=True))
    view_count = db.Column(db.Integer, default=0)  # 文章觀看次數
    # 修正backref名稱
    comments = db.relationship('Comment', backref='post', lazy=True, cascade="all, delete-orphan")

# 定義 Comment 模型
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    author = db.relationship('User', backref=db.backref('comments', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 初始化資料庫
with app.app_context():
    db.create_all()
    db.session.execute(text('PRAGMA foreign_keys = ON'))  # 開啟外鍵支持

# 首頁路由，顯示文章列表和最熱門的文章
@app.route('/')
def index():
    posts = Post.query.all()
    authors = User.query.all()
    # 查詢觀看次數最多的前三篇文章
    top_posts = Post.query.order_by(Post.view_count.desc()).limit(3).all()
    return render_template('index.html', posts=posts, authors=authors, top_posts=top_posts)

# 顯示單篇文章路由並處理留言提交
@app.route('/posts/<int:post_id>', methods=['GET', 'POST'])
def get_post(post_id):
    post = Post.query.get_or_404(post_id)

    # 增加觀看次數
    post.view_count += 1
    db.session.commit()

    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('請先登入才能留言')
            return redirect(url_for('login'))

        comment_content = request.form['comment']
        new_comment = Comment(content=comment_content, author_id=current_user.id, post_id=post.id)
        db.session.add(new_comment)
        db.session.commit()
        return redirect(url_for('get_post', post_id=post.id))

    comments = Comment.query.filter_by(post_id=post.id).all()
    return render_template('post.html', post=post, comments=comments)

# 註冊路由
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        name = request.form.get('name')
        password = request.form.get('password')

        if not username or not name or not password:
            flash('所有欄位都是必填的')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('使用者名稱已存在')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, name=name, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('register.html')

# 登入路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('登入失敗，請檢查使用者名稱和密碼')
            return redirect(url_for('login'))

    return render_template('login.html')

# 登出路由
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# 創建文章路由
@app.route('/posts/new', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        # 處理圖片上傳
        image = request.files.get('image')
        image_path = None
        if image:
            if image.filename == '':
                flash('未選擇圖片')
                return redirect(url_for('new_post'))
            if image:
                image_path = secure_filename(image.filename)  # 只保留檔名
                image.save(os.path.join(app.config['UPLOAD_FOLDER'], image_path))

        new_post = Post(title=title, content=content, image_path=image_path, author_id=current_user.id)
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('index'))

    return render_template('new_post.html')

# 編輯文章路由
@app.route('/posts/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)

    if post.author_id != current_user.id:
        flash('你無權編輯此文章')
        return redirect(url_for('index'))

    if request.method == 'POST':
        post.title = request.form['title']
        post.content = request.form['content']

        # 處理圖片上傳
        image = request.files.get('image')
        if image:
            if image.filename == '':
                flash('未選擇圖片')
                return redirect(url_for('edit_post', post_id=post.id))
            image_path = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], image_path))  # 儲存圖片
            post.image_path = image_path  # 更新文章的圖片路徑

        db.session.commit()
        return redirect(url_for('get_post', post_id=post.id))

    return render_template('edit_post.html', post=post)

# 刪除文章路由
@app.route('/posts/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)

    if post.author_id != current_user.id:
        flash('你無權刪除此文章')
        return redirect(url_for('index'))

    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('index'))

# 透過作者篩選文章的路由
@app.route('/author/<int:author_id>')
def posts_by_author(author_id):
    author = User.query.get_or_404(author_id)
    posts = Post.query.filter_by(author_id=author.id).all()
    return render_template('author_posts.html', posts=posts, author=author)

# 顯示我的文章路由
@app.route('/my_posts')
@login_required
def my_posts():
    posts = Post.query.filter_by(author_id=current_user.id).all()
    return render_template('my_posts.html', posts=posts)

if __name__ == '__main__':
    app.run(debug=True)
