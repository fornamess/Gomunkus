from flask import Flask, render_template, jsonify, request, session, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import os
import json
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
import secrets
import pymysql

pymysql.install_as_MySQLdb()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Настройка базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///charity_farm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/images'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 час

# Инициализация компонентов безопасности
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'
login_manager.login_message_category = 'info'

# Настройка ограничителя запросов
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=["200 per day", "50 per hour"]
)

# Настройка HTTPS и заголовков безопасности
talisman = Talisman(
    app,
    force_https=True,
    strict_transport_security=True,
    session_cookie_secure=True,
    content_security_policy={
        'default-src': "'self'",
        'script-src': "'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://code.jquery.com",
        'style-src': "'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
        'img-src': "'self' data: https:",
        'font-src': "'self' https://cdnjs.cloudflare.com",
        'connect-src': "'self'"
    }
)

# Защита от CSRF
csrf = CSRFProtect(app)

# Контекстный процессор для добавления текущей даты во все шаблоны
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Модели данных
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    balance = db.Column(db.Float, default=0.0)
    experience = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    last_tap = db.Column(db.DateTime)
    total_help = db.Column(db.Float, default=0.0)
    completed_projects = db.Column(db.Integer, default=0)  # Исправлено с projects_completed
    created_at = db.Column(db.DateTime, default=datetime.now)
    donations = db.relationship('Donation', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0.0)
    country = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    image = db.Column(db.String(200), default='default_project.jpg')
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.now)
    donations = db.relationship('Donation', backref='project', lazy=True)

    def progress(self):
        return (self.current_amount / self.target_amount) * 100

class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Upgrade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    effect_type = db.Column(db.String(50), nullable=False)  # 'tap_reward', 'afk_reward', 'experience'
    effect_value = db.Column(db.Float, nullable=False)
    level = db.Column(db.Integer, default=0)  # Начинаем с 0 уровня
    max_level = db.Column(db.Integer, default=10)
    base_cost = db.Column(db.Float, nullable=False)  # Базовая стоимость для расчета

    def get_current_cost(self):
        return self.base_cost * (1.5 ** self.level)  # Увеличиваем стоимость с каждым уровнем

class AFKStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    last_afk_check = db.Column(db.DateTime, default=datetime.now)
    afk_earnings = db.Column(db.Float, default=0.0)
    afk_multiplier = db.Column(db.Float, default=1.0)

# Константы
TAP_REWARD = 0.01  # Награда за тап
TAP_COOLDOWN = 1  # Задержка между тапами в секундах
LEVEL_MULTIPLIER = 1.1  # Множитель награды за уровень

# Инициализация проектов
def init_projects():
    projects = [
        {
            'title': 'Школа в Кении',
            'description': 'Строительство школы для детей в сельской местности Кении',
            'target_amount': 50000.0,
            'country': 'Кения',
            'category': 'Образование',
            'image': 'kenya_school.jpg'
        },
        {
            'title': 'Магазин продуктов',
            'description': 'Открытие продуктового магазина для местных жителей',
            'target_amount': 10000.0,
            'country': 'Гана',
            'category': 'Питание',
            'image': 'food_store.jpg'
        },
        {
            'title': 'Дом человеку на Гаити',
            'description': 'Построить дом для нуждающейся семьи на Гаити',
            'target_amount': 30000.0,
            'country': 'Гаити',
            'category': 'Жильё',
            'image': 'haiti_house.jpg'
        },
        {
            'title': 'Велик ребенку',
            'description': 'Подарить велосипед ребенку из малообеспеченной семьи',
            'target_amount': 2000.0,
            'country': 'Индия',
            'category': 'Досуг',
            'image': 'child_bike.jpg'
        },
        {
            'title': 'Шоколадка рандомному ребенку',
            'description': 'Подарить шоколадку случайному ребенку',
            'target_amount': 200.0,
            'country': 'Россия',
            'category': 'Подарки',
            'image': 'random_chocolate.jpg'
        },
        {
            'title': 'Книга Python для детей',
            'description': 'Подарить книгу "Python для детей" талантливому школьнику',
            'target_amount': 1000.0,
            'country': 'Россия',
            'category': 'Образование',
            'image': 'python_book.jpg'
        },
        {
            'title': 'Детский дом',
            'description': 'Помочь детскому дому с ремонтом и оборудованием',
            'target_amount': 100000.0,
            'country': 'Украина',
            'category': 'Социальная поддержка',
            'image': 'orphanage.jpg'
        }
    ]
    
    for project_data in projects:
        if not Project.query.filter_by(title=project_data['title']).first():
            project = Project(**project_data)
            db.session.add(project)
    
    db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # Ограничение попыток входа
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Проверка на пустые поля
        if not username or not password:
            flash('Пожалуйста, заполните все поля', 'error')
            return redirect(url_for('login'))
            
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('index')
            flash('Вы успешно вошли в систему!', 'success')
            return redirect(next_page)
        else:
            flash('Неверное имя пользователя или пароль', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per hour")  # Ограничение регистраций
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Валидация данных
        if not username or not password or not confirm_password:
            flash('Пожалуйста, заполните все поля', 'error')
            return redirect(url_for('register'))
            
        if len(username) < 3 or len(username) > 20:
            flash('Имя пользователя должно быть от 3 до 20 символов', 'error')
            return redirect(url_for('register'))
            
        if len(password) < 8:
            flash('Пароль должен быть не менее 8 символов', 'error')
            return redirect(url_for('register'))
            
        if password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return redirect(url_for('register'))
            
        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует', 'error')
            return redirect(url_for('register'))
            
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Регистрация успешна! Теперь вы можете войти', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    projects = Project.query.filter_by(status='active').all()
    return render_template('index.html', projects=projects)

@app.route('/tap', methods=['POST'])
@login_required
def tap():
    if not current_user.last_tap or (datetime.now() - current_user.last_tap).total_seconds() >= TAP_COOLDOWN:
        # Получаем множитель от улучшения тапа
        tap_upgrade = Upgrade.query.filter_by(effect_type='tap_reward').first()
        tap_multiplier = 1.0
        if tap_upgrade:
            tap_multiplier = 1 + (tap_upgrade.level * tap_upgrade.effect_value)
        
        reward = TAP_REWARD * tap_multiplier * (1 + (current_user.level - 1) * 0.1)
        current_user.balance += reward
        current_user.experience += 1
        current_user.last_tap = datetime.now()
        
        # Проверка повышения уровня
        next_level_exp = current_user.level * 100
        if current_user.experience >= next_level_exp:
            current_user.level += 1
            current_user.experience = 0
            flash(f'Поздравляем! Вы достигли {current_user.level} уровня!', 'success')
        
        db.session.commit()
        return jsonify({
            'success': True,
            'reward': reward,
            'balance': current_user.balance,
            'experience': current_user.experience,
            'level': current_user.level,
            'next_level': current_user.level * 100
        })
    return jsonify({
        'success': False,
        'message': f'Подождите {TAP_COOLDOWN} секунд между тапами'
    })

@app.route('/projects')
@login_required
def projects():
    active_projects = Project.query.filter_by(status='active').all()
    completed_projects = Project.query.filter_by(status='completed').all()
    return render_template('projects.html', active_projects=active_projects, completed_projects=completed_projects)

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/help_project/<int:project_id>', methods=['POST'])
@login_required
def help_project(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({'success': False, 'message': 'Проект не найден'}), 404
        
    try:
        amount = float(request.form.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Неверная сумма'}), 400
        
    if amount <= 0:
        return jsonify({'success': False, 'message': 'Сумма должна быть больше 0'}), 400
        
    if current_user.balance < amount:
        return jsonify({'success': False, 'message': 'Недостаточно средств'}), 400
        
    current_user.balance -= amount
    project.current_amount += amount
    current_user.total_help += amount
    
    donation = Donation(user_id=current_user.id, project_id=project.id, amount=amount)
    db.session.add(donation)
    
    if project.current_amount >= project.target_amount:
        project.status = 'completed'
        current_user.completed_projects += 1
    
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Спасибо за вашу помощь!',
        'project_progress': project.progress(),
        'user_balance': current_user.balance,
        'total_help': current_user.total_help
    })

@app.route('/user_stats')
@login_required
def user_stats():
    next_level_exp = current_user.level * 100
    return jsonify({
        'balance': current_user.balance,
        'level': current_user.level,
        'experience': current_user.experience,
        'next_level': next_level_exp,
        'total_help': current_user.total_help,
        'completed_projects': current_user.completed_projects
    })

@app.route('/afk_earnings', methods=['GET'])
@login_required
def afk_earnings():
    # Проверяем, есть ли у пользователя улучшение AFK заработка
    afk_upgrade = Upgrade.query.filter_by(effect_type='afk_reward').first()
    if not afk_upgrade or afk_upgrade.level == 0:
        return jsonify({
            'success': True,
            'earnings': 0,
            'new_balance': current_user.balance,
            'message': 'Купите улучшение AFK заработка для получения пассивного дохода'
        })
    
    afk_stats = AFKStats.query.filter_by(user_id=current_user.id).first()
    if not afk_stats:
        afk_stats = AFKStats(user_id=current_user.id)
        db.session.add(afk_stats)
        db.session.commit()
    
    time_diff = (datetime.now() - afk_stats.last_afk_check).total_seconds()
    base_earnings = (time_diff / 3600) * 10  # 10 монет в час базово
    earnings = base_earnings * afk_stats.afk_multiplier
    
    current_user.balance += earnings
    afk_stats.afk_earnings += earnings
    afk_stats.last_afk_check = datetime.now()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'earnings': earnings,
        'total_afk_earnings': afk_stats.afk_earnings,
        'new_balance': current_user.balance
    })

@app.route('/upgrades')
@login_required
def upgrades():
    upgrades = Upgrade.query.all()
    return render_template('upgrades.html', upgrades=upgrades)

@app.route('/purchase_upgrade/<int:upgrade_id>', methods=['POST'])
@login_required
def purchase_upgrade(upgrade_id):
    upgrade = Upgrade.query.get_or_404(upgrade_id)
    
    if upgrade.level >= upgrade.max_level:
        return jsonify({'success': False, 'message': 'Достигнут максимальный уровень улучшения'})
    
    current_cost = upgrade.get_current_cost()
    if current_user.balance < current_cost:
        return jsonify({'success': False, 'message': 'Недостаточно средств'})
    
    current_user.balance -= current_cost
    upgrade.level += 1
    upgrade.cost = current_cost
    
    # Применяем эффект улучшения
    if upgrade.effect_type == 'tap_reward':
        global TAP_REWARD
        TAP_REWARD *= (1 + upgrade.effect_value)
    elif upgrade.effect_type == 'afk_reward':
        afk_stats = AFKStats.query.filter_by(user_id=current_user.id).first()
        if not afk_stats:
            afk_stats = AFKStats(user_id=current_user.id)
            db.session.add(afk_stats)
        afk_stats.afk_multiplier *= (1 + upgrade.effect_value)
    
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Улучшение успешно приобретено',
        'new_balance': current_user.balance,
        'upgrade_level': upgrade.level,
        'next_cost': upgrade.get_current_cost()
    })

def init_upgrades():
    upgrades = [
        {
            'name': 'Улучшенный тап',
            'description': 'Увеличивает награду за тап на 10%',
            'base_cost': 100.0,
            'effect_type': 'tap_reward',
            'effect_value': 0.1
        },
        {
            'name': 'AFK заработок',
            'description': 'Увеличивает AFK заработок на 15%',
            'base_cost': 500.0,
            'effect_type': 'afk_reward',
            'effect_value': 0.15
        },
        {
            'name': 'Опыт',
            'description': 'Увеличивает получаемый опыт на 20%',
            'base_cost': 200.0,
            'effect_type': 'experience',
            'effect_value': 0.2
        }
    ]
    
    for upgrade_data in upgrades:
        if not Upgrade.query.filter_by(name=upgrade_data['name']).first():
            upgrade = Upgrade(
                name=upgrade_data['name'],
                description=upgrade_data['description'],
                cost=upgrade_data['base_cost'],
                base_cost=upgrade_data['base_cost'],
                effect_type=upgrade_data['effect_type'],
                effect_value=upgrade_data['effect_value'],
                level=0
            )
            db.session.add(upgrade)
    
    db.session.commit()

# Инициализация базы данных
def init_db():
    with app.app_context():
        db.create_all()
        # Удаляем старые проекты (если нужно)
        Project.query.delete()
        db.session.commit()
        # Добавляем новые проекты
        init_projects()
        # Добавляем улучшения
        init_upgrades()

if __name__ == '__main__':
    init_db()
    # Для продакшена используем переменные окружения
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug) 