# E:\FreshiFy_Mobile_App_Backend\app\routes\auth_routes.py
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps
import os
from bson import ObjectId

auth_bp = Blueprint('auth', __name__)

# Secret key for JWT (add this to your .env file)
SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this')

# Import your database connection
from app.db.mongodb_handler import FreshiFyDB
db = FreshiFyDB()

# JWT token required decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token.split(' ')[1]
            
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            current_user = db.db['users'].find_one({'_id': ObjectId(data['user_id'])})
            
            if not current_user:
                return jsonify({'message': 'User not found!'}), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token!'}), 401
        except Exception as e:
            return jsonify({'message': f'Token validation error: {str(e)}'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated

@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'email', 'password']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'message': f'{field} is required'}), 400
        
        name = data['name'].strip()
        email = data['email'].strip().lower()
        password = data['password']
        
        # Validate email format
        if '@' not in email or '.' not in email:
            return jsonify({'message': 'Invalid email format'}), 400
        
        # Validate password length
        if len(password) < 6:
            return jsonify({'message': 'Password must be at least 6 characters'}), 400
        
        # Check if user already exists
        existing_user = db.db['users'].find_one({'email': email})
        if existing_user:
            return jsonify({'message': 'Email already registered'}), 409
        
        # Hash password
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        # Create user document
        user_doc = {
            'name': name,
            'email': email,
            'password': hashed_password,
            'avatar': data.get('avatar', ''),
            'bio': data.get('bio', 'Sustainable Living Advocate 🌿'),
            'createdAt': datetime.datetime.now(datetime.timezone.utc),
            'updatedAt': datetime.datetime.now(datetime.timezone.utc),
        }
        
        # Insert user
        result = db.db['users'].insert_one(user_doc)
        user_id = str(result.inserted_id)
        
        # Generate JWT token
        token = jwt.encode({
            'user_id': user_id,
            'email': email,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
        }, SECRET_KEY, algorithm="HS256")
        
        return jsonify({
            'message': 'Registration successful',
            'token': token,
            'user': {
                'id': user_id,
                'name': name,
                'email': email,
                'avatar': user_doc['avatar'],
                'bio': user_doc['bio']
            }
        }), 201
        
    except Exception as e:
        return jsonify({'message': f'Registration failed: {str(e)}'}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('email') or not data.get('password'):
            return jsonify({'message': 'Email and password are required'}), 400
        
        email = data['email'].strip().lower()
        password = data['password']
        
        # Find user
        user = db.db['users'].find_one({'email': email})
        
        if not user:
            return jsonify({'message': 'Invalid email or password'}), 401
        
        # Check password
        if not check_password_hash(user['password'], password):
            return jsonify({'message': 'Invalid email or password'}), 401
        
        # Generate JWT token
        token = jwt.encode({
            'user_id': str(user['_id']),
            'email': email,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
        }, SECRET_KEY, algorithm="HS256")
        
        return jsonify({
            'message': 'Login successful',
            'token': token,
            'user': {
                'id': str(user['_id']),
                'name': user['name'],
                'email': user['email'],
                'avatar': user.get('avatar', ''),
                'bio': user.get('bio', 'Sustainable Living Advocate 🌿')
            }
        }), 200
        
    except Exception as e:
        return jsonify({'message': f'Login failed: {str(e)}'}), 500

@auth_bp.route('/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    """Get current user profile"""
    try:
        return jsonify({
            'user': {
                'id': str(current_user['_id']),
                'name': current_user['name'],
                'email': current_user['email'],
                'avatar': current_user.get('avatar', ''),
                'bio': current_user.get('bio', 'Sustainable Living Advocate 🌿'),
                'createdAt': current_user.get('createdAt')
            }
        }), 200
    except Exception as e:
        return jsonify({'message': f'Failed to get profile: {str(e)}'}), 500

@auth_bp.route('/profile', methods=['PUT'])
@token_required
def update_profile(current_user):
    """Update user profile"""
    try:
        data = request.get_json()
        
        update_fields = {}
        if 'name' in data:
            update_fields['name'] = data['name'].strip()
        if 'bio' in data:
            update_fields['bio'] = data['bio'].strip()
        if 'avatar' in data:
            update_fields['avatar'] = data['avatar']
        
        update_fields['updatedAt'] = datetime.datetime.now(datetime.timezone.utc)
        
        # Update user
        db.db['users'].update_one(
            {'_id': current_user['_id']},
            {'$set': update_fields}
        )
        
        # Get updated user
        updated_user = db.db['users'].find_one({'_id': current_user['_id']})
        
        return jsonify({
            'message': 'Profile updated successfully',
            'user': {
                'id': str(updated_user['_id']),
                'name': updated_user['name'],
                'email': updated_user['email'],
                'avatar': updated_user.get('avatar', ''),
                'bio': updated_user.get('bio', '')
            }
        }), 200
        
    except Exception as e:
        return jsonify({'message': f'Failed to update profile: {str(e)}'}), 500

@auth_bp.route('/change-password', methods=['POST'])
@token_required
def change_password(current_user):
    """Change user password"""
    try:
        data = request.get_json()
        
        old_password = data.get('oldPassword')
        new_password = data.get('newPassword')
        
        if not old_password or not new_password:
            return jsonify({'message': 'Old and new passwords are required'}), 400
        
        # Verify old password
        if not check_password_hash(current_user['password'], old_password):
            return jsonify({'message': 'Current password is incorrect'}), 401
        
        # Validate new password
        if len(new_password) < 6:
            return jsonify({'message': 'New password must be at least 6 characters'}), 400
        
        # Hash new password
        hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')
        
        # Update password
        db.db['users'].update_one(
            {'_id': current_user['_id']},
            {'$set': {
                'password': hashed_password,
                'updatedAt': datetime.datetime.now(datetime.timezone.utc)
            }}
        )
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        return jsonify({'message': f'Failed to change password: {str(e)}'}), 500