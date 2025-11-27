# E:\FreshiFy_Mobile_App_Backend\Auth_Service.py
"""
FreshiFy Authentication Service (Enhanced with Health Profile)
Port: 5003
Handles user registration, login, profile management, JWT authentication, and health profiles
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps
import os
import sys
from dotenv import load_dotenv
from bson import ObjectId
import logging

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

# Load environment
load_dotenv()

# Initialize Flask
app = Flask(__name__)
CORS(app, origins=os.getenv('CORS_ORIGINS', '*').split(','))

# Secret key for JWT
SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this')

# Import database
from DB_FreshiFy import FreshiFyDB
db = FreshiFyDB()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# JWT Token Decorator
# ============================================================================
def token_required(f):
    """Decorator to validate JWT tokens"""
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
            logger.error(f"Token validation error: {str(e)}")
            return jsonify({'message': f'Token validation error: {str(e)}'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated

# ============================================================================
# Helper Functions
# ============================================================================
def extract_health_profile(data):
    """Extract health profile fields from request data"""
    health_fields = [
        'Age', 'Gender', 'Height_cm', 'Weight_kg', 'BMI',
        'Chronic_Disease', 'Blood_Pressure_Systolic', 'Blood_Pressure_Diastolic',
        'Cholesterol_Level', 'Blood_Sugar_Level', 'Genetic_Risk_Factor',
        'Allergies', 'Daily_Steps', 'Exercise_Frequency', 'Sleep_Hours',
        'Alcohol_Consumption', 'Smoking_Habit', 'Dietary_Habits',
        'Caloric_Intake', 'Protein_Intake', 'Carbohydrate_Intake', 'Fat_Intake',
        'Preferred_Cuisine', 'Food_Aversions', 'Recommended_Calories',
        'Recommended_Protein', 'Recommended_Carbs', 'Recommended_Fats',
        'Recommended_Meal_Plan'
    ]
    
    health_profile = {}
    for field in health_fields:
        if field in data:
            value = data[field]
            # Convert numeric fields to appropriate type
            if field in ['Age', 'Height_cm', 'Weight_kg', 'Blood_Pressure_Systolic',
                        'Blood_Pressure_Diastolic', 'Cholesterol_Level', 'Blood_Sugar_Level',
                        'Daily_Steps', 'Caloric_Intake', 'Protein_Intake',
                        'Carbohydrate_Intake', 'Fat_Intake', 'Recommended_Calories',
                        'Recommended_Protein', 'Recommended_Carbs', 'Recommended_Fats']:
                try:
                    health_profile[field] = int(value) if value != '' else None
                except (ValueError, TypeError):
                    health_profile[field] = None
            elif field in ['BMI', 'Sleep_Hours']:
                try:
                    health_profile[field] = float(value) if value != '' else None
                except (ValueError, TypeError):
                    health_profile[field] = None
            else:
                health_profile[field] = value if value != '' else None
    
    return health_profile if health_profile else None

# ============================================================================
# Authentication Endpoints
# ============================================================================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register a new user with optional health profile"""
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
        
        # Extract health profile (optional)
        health_profile = extract_health_profile(data)
        
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
        
        # Add health profile if provided
        if health_profile:
            user_doc['healthProfile'] = health_profile
        
        # Insert user
        result = db.db['users'].insert_one(user_doc)
        user_id = str(result.inserted_id)
        
        # Generate JWT token (30 days expiry)
        token = jwt.encode({
            'user_id': user_id,
            'email': email,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
        }, SECRET_KEY, algorithm="HS256")
        
        logger.info(f"✅ New user registered: {email} (health profile: {bool(health_profile)})")
        
        return jsonify({
            'message': 'Registration successful',
            'token': token,
            'user': {
                'id': user_id,
                'name': name,
                'email': email,
                'avatar': user_doc['avatar'],
                'bio': user_doc['bio'],
                'hasHealthProfile': bool(health_profile)
            }
        }), 201
        
    except Exception as e:
        logger.error(f"❌ Registration error: {str(e)}")
        return jsonify({'message': f'Registration failed: {str(e)}'}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.get_json()
        
        if not data.get('email') or not data.get('password'):
            return jsonify({'message': 'Email and password are required'}), 400
        
        email = data['email'].strip().lower()
        password = data['password']
        
        user = db.db['users'].find_one({'email': email})
        
        if not user:
            return jsonify({'message': 'Invalid email or password'}), 401
        
        if not check_password_hash(user['password'], password):
            return jsonify({'message': 'Invalid email or password'}), 401
        
        token = jwt.encode({
            'user_id': str(user['_id']),
            'email': email,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
        }, SECRET_KEY, algorithm="HS256")
        
        logger.info(f"✅ User logged in: {email}")
        
        return jsonify({
            'message': 'Login successful',
            'token': token,
            'user': {
                'id': str(user['_id']),
                'name': user['name'],
                'email': user['email'],
                'avatar': user.get('avatar', ''),
                'bio': user.get('bio', 'Sustainable Living Advocate 🌿'),
                'hasHealthProfile': 'healthProfile' in user
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Login error: {str(e)}")
        return jsonify({'message': f'Login failed: {str(e)}'}), 500


@app.route('/api/auth/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    """Get current user profile with health data"""
    try:
        user_data = {
            'id': str(current_user['_id']),
            'name': current_user['name'],
            'email': current_user['email'],
            'avatar': current_user.get('avatar', ''),
            'bio': current_user.get('bio', 'Sustainable Living Advocate 🌿'),
            'createdAt': current_user.get('createdAt').isoformat() if current_user.get('createdAt') else None
        }
        
        if 'healthProfile' in current_user:
            user_data['healthProfile'] = current_user['healthProfile']
        
        return jsonify({'user': user_data}), 200
    except Exception as e:
        logger.error(f"❌ Get profile error: {str(e)}")
        return jsonify({'message': f'Failed to get profile: {str(e)}'}), 500


@app.route('/api/auth/profile', methods=['PUT'])
@token_required
def update_profile(current_user):
    """Update user profile (basic info and/or health profile)"""
    try:
        data = request.get_json()
        
        update_fields = {}
        
        # Basic profile updates
        if 'name' in data and data['name']:
            update_fields['name'] = data['name'].strip()
        if 'bio' in data:
            update_fields['bio'] = data['bio'].strip()
        if 'avatar' in data:
            update_fields['avatar'] = data['avatar']
        
        # Health profile updates
        health_profile = extract_health_profile(data)
        if health_profile:
            update_fields['healthProfile'] = health_profile
        
        if not update_fields:
            return jsonify({'message': 'No fields to update'}), 400
        
        update_fields['updatedAt'] = datetime.datetime.now(datetime.timezone.utc)
        
        db.db['users'].update_one(
            {'_id': current_user['_id']},
            {'$set': update_fields}
        )
        
        updated_user = db.db['users'].find_one({'_id': current_user['_id']})
        
        logger.info(f"✅ Profile updated: {current_user['email']}")
        
        response_data = {
            'message': 'Profile updated successfully',
            'user': {
                'id': str(updated_user['_id']),
                'name': updated_user['name'],
                'email': updated_user['email'],
                'avatar': updated_user.get('avatar', ''),
                'bio': updated_user.get('bio', ''),
                'hasHealthProfile': 'healthProfile' in updated_user
            }
        }
        
        if 'healthProfile' in updated_user:
            response_data['user']['healthProfile'] = updated_user['healthProfile']
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"❌ Update profile error: {str(e)}")
        return jsonify({'message': f'Failed to update profile: {str(e)}'}), 500


@app.route('/api/auth/health-profile', methods=['GET'])
@token_required
def get_health_profile(current_user):
    """Get user's health profile"""
    try:
        if 'healthProfile' not in current_user:
            return jsonify({'message': 'No health profile found'}), 404
        
        return jsonify({
            'healthProfile': current_user['healthProfile']
        }), 200
    except Exception as e:
        logger.error(f"❌ Get health profile error: {str(e)}")
        return jsonify({'message': f'Failed to get health profile: {str(e)}'}), 500


@app.route('/api/auth/health-profile', methods=['PUT'])
@token_required
def update_health_profile(current_user):
    """Update user's health profile"""
    try:
        data = request.get_json()
        health_profile = extract_health_profile(data)
        
        if not health_profile:
            return jsonify({'message': 'No health profile data provided'}), 400
        
        db.db['users'].update_one(
            {'_id': current_user['_id']},
            {'$set': {
                'healthProfile': health_profile,
                'updatedAt': datetime.datetime.now(datetime.timezone.utc)
            }}
        )
        
        logger.info(f"✅ Health profile updated: {current_user['email']}")
        
        return jsonify({
            'message': 'Health profile updated successfully',
            'healthProfile': health_profile
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Update health profile error: {str(e)}")
        return jsonify({'message': f'Failed to update health profile: {str(e)}'}), 500


@app.route('/api/auth/change-password', methods=['POST'])
@token_required
def change_password(current_user):
    """Change user password"""
    try:
        data = request.get_json()
        
        old_password = data.get('oldPassword')
        new_password = data.get('newPassword')
        
        if not old_password or not new_password:
            return jsonify({'message': 'Old and new passwords are required'}), 400
        
        if not check_password_hash(current_user['password'], old_password):
            return jsonify({'message': 'Current password is incorrect'}), 401
        
        if len(new_password) < 6:
            return jsonify({'message': 'New password must be at least 6 characters'}), 400
        
        hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')
        
        db.db['users'].update_one(
            {'_id': current_user['_id']},
            {'$set': {
                'password': hashed_password,
                'updatedAt': datetime.datetime.now(datetime.timezone.utc)
            }}
        )
        
        logger.info(f"✅ Password changed: {current_user['email']}")
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        logger.error(f"❌ Change password error: {str(e)}")
        return jsonify({'message': f'Failed to change password: {str(e)}'}), 500


@app.route('/api/auth/verify', methods=['GET'])
@token_required
def verify_token(current_user):
    """Verify if token is valid"""
    try:
        return jsonify({
            'message': 'Token is valid',
            'user': {
                'id': str(current_user['_id']),
                'name': current_user['name'],
                'email': current_user['email'],
                'hasHealthProfile': 'healthProfile' in current_user
            }
        }), 200
    except Exception as e:
        logger.error(f"❌ Verify token error: {str(e)}")
        return jsonify({'message': f'Token verification failed: {str(e)}'}), 500


@app.route('/api/auth/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Auth Service',
        'version': '1.1.0',
        'features': ['basic_auth', 'health_profile'],
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
    }), 200


# ============================================================================
# Run Server
# ============================================================================
if __name__ == '__main__':
    PORT = int(os.getenv('AUTH_PORT', 5003))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    logger.info("=" * 60)
    logger.info("🔐 FreshiFy Authentication Service (Enhanced)")
    logger.info("=" * 60)
    logger.info(f"📍 Starting on: http://0.0.0.0:{PORT}")
    logger.info(f"🔧 Debug mode: {DEBUG}")
    logger.info(f"🗄️  Database: {os.getenv('DB_NAME', 'DB_FreshiFy')}")
    logger.info(f"✨ Features: Basic Auth + Health Profile")
    logger.info("=" * 60)
    
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=DEBUG
    )