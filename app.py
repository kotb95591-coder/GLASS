from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Message, Channel, Invitation, Chat  # ← ДОБАВИТЬ Chat здесь
from config import Config
from datetime import datetime
import json

app = Flask(__name__)
app.config.from_object(Config)

# Инициализация расширений
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def is_admin():  # ← ИСПРАВЛЕНО ЗДЕСЬ (добавлено :)
    return current_user.is_authenticated and current_user.username == '@'


# Маршруты
@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main'))

    register_mode = request.args.get('register') == 'true'

    if request.method == 'POST':
        if not register_mode:
            username = request.form.get('username')
            password = request.form.get('password')
            user = User.query.filter_by(username=username).first()

            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for('main'))
            flash('Неверное имя пользователя или пароль')

    return render_template('login.html', register=register_mode)


@app.route('/register', methods=['POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main'))

    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')

    if password != confirm_password:
        flash('Пароли не совпадают')
        return render_template('login.html', register=True)

    if User.query.filter_by(username=username).first():
        flash('Имя пользователя уже занято')
        return render_template('login.html', register=True)

    if User.query.filter_by(email=email).first():
        flash('Email уже используется')
        return render_template('login.html', register=True)

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    welcome_msg = Message(
        sender_id=1,
        receiver_id=user.id,
        content='Добро пожаловать в GSLASE! Здесь вы можете общаться с другими пользователями.',
        content_type='text',
        timestamp=datetime.utcnow()
    )
    db.session.add(welcome_msg)
    db.session.commit()

    login_user(user)
    flash('Регистрация успешна! Добро пожаловать в GSLASE!')
    return redirect(url_for('main'))


@app.route('/main')
@login_required
def main():
    personal_messages = Message.query.filter(
        (Message.receiver_id == current_user.id) |
        (Message.sender_id == current_user.id)
    ).order_by(Message.timestamp.asc()).all()

    invitations = Invitation.query.filter_by(invited_user_id=current_user.id, status='pending').all()

    return render_template('main.html',
                           user=current_user,
                           messages=personal_messages,
                           invitations=invitations)


@app.route('/api/create_chat', methods=['POST'])
@login_required
def create_chat():
    try:
        data = request.get_json()
        receiver_id = data.get('receiver_id')

        # Проверяем, существует ли уже чат
        existing_chat = Chat.query.filter(
            ((Chat.user1_id == current_user.id) & (Chat.user2_id == receiver_id)) |
            ((Chat.user1_id == receiver_id) & (Chat.user2_id == current_user.id))
        ).first()

        if existing_chat:
            return jsonify({'status': 'success', 'chat_id': existing_chat.id})

        # Создаем новый чат
        new_chat = Chat(
            user1_id=current_user.id,
            user2_id=receiver_id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_chat)
        db.session.commit()

        return jsonify({'status': 'success', 'chat_id': new_chat.id})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/user_chats')
@login_required
def get_user_chats():
    try:
        # Получаем все чаты пользователя
        chats = Chat.query.filter(
            (Chat.user1_id == current_user.id) | (Chat.user2_id == current_user.id)
        ).all()

        chats_data = []
        for chat in chats:
            # Определяем собеседника
            if chat.user1_id == current_user.id:
                other_user = User.query.get(chat.user2_id)
            else:
                other_user = User.query.get(chat.user1_id)

            # Получаем последнее сообщение в чате
            last_message = Message.query.filter(
                ((Message.sender_id == current_user.id) & (Message.receiver_id == other_user.id)) |
                ((Message.sender_id == other_user.id) & (Message.receiver_id == current_user.id))
            ).order_by(Message.timestamp.desc()).first()

            chats_data.append({
                'chat_id': chat.id,
                'other_user_id': other_user.id,
                'other_username': other_user.username,
                'last_message': last_message.content if last_message else 'Нет сообщений',
                'last_message_time': last_message.timestamp.isoformat() if last_message else None
            })

        return jsonify({'status': 'success', 'chats': chats_data})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html', user=current_user)


@app.route('/admin')
@login_required
def admin_panel():
    if not is_admin():
        flash('Доступ запрещен')
        return redirect(url_for('main'))

    users = User.query.all()
    return render_template('admin.html', user=current_user, users=users)


@app.route('/api/search_users')
@login_required
def search_users():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'users': []})

    try:
        # Ищем пользователей по username (кроме текущего и бота)
        users = User.query.filter(
            User.username.ilike(f'%{query}%'),
            User.id != current_user.id,
            User.id != 1
        ).limit(10).all()

        users_data = [{
            'id': user.id,
            'username': user.username,
            'avatar': user.avatar_url
        } for user in users]

        return jsonify({'status': 'success', 'users': users_data})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    try:
        data = request.get_json()
        content = data.get('content', '').strip()
        receiver_id = data.get('receiver_id')

        if not content:
            return jsonify({'status': 'error', 'message': 'Сообщение не может быть пустым'})

        message = Message(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            content=content,
            content_type='text',
            timestamp=datetime.utcnow()
        )

        db.session.add(message)
        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': {
                'id': message.id,
                'content': message.content,
                'sender': current_user.username,
                'timestamp': message.timestamp.isoformat()
            }
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/messages/<int:receiver_id>')
@login_required
def get_messages(receiver_id):
    try:
        if receiver_id == 1:
            messages = Message.query.filter(
                ((Message.receiver_id == current_user.id) & (Message.sender_id == 1)) |
                ((Message.sender_id == current_user.id) & (Message.receiver_id == 1))
            ).order_by(Message.timestamp.asc()).all()
        else:
            messages = Message.query.filter(
                ((Message.sender_id == current_user.id) & (Message.receiver_id == receiver_id)) |
                ((Message.sender_id == receiver_id) & (Message.receiver_id == current_user.id))
            ).order_by(Message.timestamp.asc()).all()

        messages_data = []
        for msg in messages:
            messages_data.append({
                'id': msg.id,
                'content': msg.content,
                'sender': msg.sender.username if msg.sender else 'Unknown',
                'timestamp': msg.timestamp.isoformat(),
                'is_own': msg.sender_id == current_user.id,
                'content_type': msg.content_type,
                'invitation_id': msg.invitation_id
            })

        return jsonify({'status': 'success', 'messages': messages_data})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/invite/send', methods=['POST'])
@login_required
def send_invitation():
    try:
        data = request.get_json()
        invited_username = data.get('username')
        channel_name = data.get('channel_name')

        invited_user = User.query.filter_by(username=invited_username).first()
        if not invited_user:
            return jsonify({'status': 'error', 'message': 'Пользователь не найден'})

        invitation = Invitation(
            inviter_id=current_user.id,
            invited_user_id=invited_user.id,
            channel_name=channel_name,
            status='pending'
        )
        db.session.add(invitation)
        db.session.flush()

        bot_message = Message(
            sender_id=1,
            receiver_id=invited_user.id,
            content=f'🎉 {current_user.username} приглашает вас в канал "{channel_name}"',
            content_type='invitation',
            invitation_id=invitation.id,
            timestamp=datetime.utcnow()
        )
        db.session.add(bot_message)
        db.session.commit()

        return jsonify({'status': 'success', 'message': 'Приглашение отправлено'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/invite/respond', methods=['POST'])
@login_required
def respond_invitation():
    try:
        data = request.get_json()
        invitation_id = data.get('invitation_id')
        accept = data.get('accept')

        invitation = Invitation.query.get(invitation_id)
        if not invitation or invitation.invited_user_id != current_user.id:
            return jsonify({'status': 'error', 'message': 'Приглашение не найдено'})

        if accept:
            invitation.status = 'accepted'
            message_content = f'✅ Вы приняли приглашение в канал "{invitation.channel_name}"'
        else:
            invitation.status = 'rejected'
            message_content = f'❌ Вы отклонили приглашение в канал "{invitation.channel_name}"'

        bot_message = Message(
            sender_id=1,
            receiver_id=current_user.id,
            content=message_content,
            content_type='text',
            timestamp=datetime.utcnow()
        )
        db.session.add(bot_message)
        db.session.commit()

        return jsonify({'status': 'success', 'message': message_content})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/admin/user_info/<username>')
@login_required
def admin_user_info(username):
    if not is_admin():
        return jsonify({'status': 'error', 'message': 'Доступ запрещен'})

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'status': 'error', 'message': 'Пользователь не найден'})

    return jsonify({
        'status': 'success',
        'user': {
            'username': user.username,
            'email': user.email,
            'glass_balance': user.glass_balance,
            'is_banned': user.is_banned,
            'created_at': user.created_at.isoformat() if user.created_at else None
        }
    })


@app.route('/api/admin/give_glass', methods=['POST'])
@login_required
def admin_give_glass():
    if not is_admin():
        return jsonify({'status': 'error', 'message': 'Доступ запрещен'})

    try:
        data = request.get_json()
        username = data.get('username')
        amount = int(data.get('amount', 0))

        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'status': 'error', 'message': 'Пользователь не найден'})

        user.glass_balance += amount
        db.session.commit()

        return jsonify({'status': 'success', 'new_balance': user.glass_balance})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/admin/give_glass_all', methods=['POST'])
@login_required
def admin_give_glass_all():
    if not is_admin():
        return jsonify({'status': 'error', 'message': 'Доступ запрещен'})

    try:
        data = request.get_json()
        amount = int(data.get('amount', 0))

        if amount <= 0:
            return jsonify({'status': 'error', 'message': 'Неверное количество'})

        users = User.query.filter(User.id != 1).all()
        for user in users:
            user.glass_balance += amount

        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': f'Выдано {amount} стеклов всем пользователям',
            'total_affected': len(users)
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/admin/ban_user', methods=['POST'])
@login_required
def admin_ban_user():
    if not is_admin():
        return jsonify({'status': 'error', 'message': 'Доступ запрещен'})

    try:
        data = request.get_json()
        username = data.get('username')

        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'status': 'error', 'message': 'Пользователь не найден'})

        user.is_banned = True
        db.session.commit()

        return jsonify({'status': 'success', 'message': f'Пользователь {username} забанен'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/admin/unban_user', methods=['POST'])
@login_required
def admin_unban_user():
    if not is_admin():
        return jsonify({'status': 'error', 'message': 'Доступ запрещен'})

    try:
        data = request.get_json()
        username = data.get('username')

        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'status': 'error', 'message': 'Пользователь не найден'})

        user.is_banned = False
        db.session.commit()

        return jsonify({'status': 'success', 'message': f'Пользователь {username} разбанен'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/admin/change_password', methods=['POST'])
@login_required
def admin_change_password():
    if not is_admin():
        return jsonify({'status': 'error', 'message': 'Доступ запрещен'})

    try:
        data = request.get_json()
        username = data.get('username')
        new_password = data.get('new_password')

        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'status': 'error', 'message': 'Пользователь не найден'})

        user.set_password(new_password)
        db.session.commit()

        return jsonify({'status': 'success', 'message': f'Пароль для {username} изменен'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# Создание таблиц и начальных данных
with app.app_context():
    db.create_all()

    bot_user = User.query.filter_by(username='GSLASE_Bot').first()
    if not bot_user:
        bot_user = User(
            username='GSLASE_Bot',
            email='bot@gslase.com',
            glass_balance=0
        )
        bot_user.set_password('bot_password')
        db.session.add(bot_user)

    admin_user = User.query.filter_by(username='@').first()
    if not admin_user:
        admin_user = User(username='@', email='admin@gslase.com')
        admin_user.set_password('admin123')
        admin_user.glass_balance = 1000
        admin_user.is_premium = True
        db.session.add(admin_user)

    db.session.commit()




if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)