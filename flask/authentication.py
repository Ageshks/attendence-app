import logging
from functools import wraps
from typing import Dict, Any, Optional
from flask import Flask, jsonify, request
from flask_mysqldb import MySQL
import MySQLdb
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
from datetime import datetime, timedelta
import jwt
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config.update({
    'SECRET_KEY': os.getenv('SECRET_KEY', 'fallback-secret-key'),
    'JWT_SECRET_KEY': os.getenv('JWT_SECRET_KEY', 'jwt-secret-key'),
    'JWT_ACCESS_TOKEN_EXPIRES': timedelta(minutes=30),
    'MYSQL_HOST': os.getenv('MYSQL_HOST', 'localhost'),
    'MYSQL_USER': os.getenv('MYSQL_USER'),
    'MYSQL_PASSWORD': os.getenv('MYSQL_PASSWORD'),
    'MYSQL_DB': os.getenv('MYSQL_DB', 'testingdb'),
    'MYSQL_CURSORCLASS': 'DictCursor'
})

CORS(app)
mysql = MySQL(app)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Helper Functions
def create_jwt_token(user_id: str, is_admin: bool = False) -> str:
    """Generate JWT token for authentication"""
    payload = {
        'sub': user_id,
        'is_admin': is_admin,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES']
    }
    return jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')

def validate_coordinates(latitude: float, longitude: float) -> bool:
    """Validate geographic coordinates"""
    return (-90 <= latitude <= 90) and (-180 <= longitude <= 180)

# Decorators
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
        
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
            
        try:
            data = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
            current_user = data['sub']
            is_admin = data.get('is_admin', False)
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 401
            
        return f(current_user, is_admin, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(current_user, is_admin, *args, **kwargs):
        if not is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        return f(current_user, is_admin, *args, **kwargs)
    return decorated

# Routes
@app.route('/api/auth/login', methods=['POST'])
def login():
    """Authenticate user and return JWT token"""
    try:
        data = request.get_json()
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({'message': 'Missing credentials'}), 400

        with mysql.connection.cursor(MySQLdb.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id, username, password, is_admin FROM user WHERE username=%s",
                (data['username'],)
            user = cursor.fetchone()

        if user and check_password_hash(user['password'], data['password']):
            token = create_jwt_token(user['username'], user['is_admin'])
            return jsonify({
                'message': 'Login successful',
                'token': token,
                'is_admin': user['is_admin']
            })

        return jsonify({'message': 'Invalid credentials'}), 401
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/attendance/checkin', methods=['POST'])
@token_required
def check_in(current_user: str, is_admin: bool):
    """Record employee check-in with location"""
    try:
        data = request.get_json()
        if not all(key in data for key in ['latitude', 'longitude']):
            return jsonify({'message': 'Missing location data'}), 400

        if not validate_coordinates(data['latitude'], data['longitude']):
            return jsonify({'message': 'Invalid coordinates'}), 400

        check_in_time = datetime.now()
        
        with mysql.connection.cursor(MySQLdb.cursors.DictCursor) as cursor:
            # Check for existing check-in today
            cursor.execute(
                "SELECT id FROM attendance WHERE username=%s AND DATE(check_in_time)=CURDATE()",
                (current_user,)
            )
            if cursor.fetchone():
                return jsonify({'message': 'Already checked in today'}), 400

            # Record check-in
            cursor.execute(
                """INSERT INTO attendance 
                (username, check_in_time, latitude, longitude) 
                VALUES (%s, %s, %s, %s)""",
                (current_user, check_in_time, data['latitude'], data['longitude'])
            )
            mysql.connection.commit()

        return jsonify({
            'message': 'Check-in recorded',
            'check_in_time': check_in_time.isoformat()
        }), 201

    except Exception as e:
        logger.error(f"Check-in error: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/attendance/checkout', methods=['POST'])
@token_required
def check_out(current_user: str, is_admin: bool):
    """Record employee check-out"""
    try:
        check_out_time = datetime.now()
        
        with mysql.connection.cursor(MySQLdb.cursors.DictCursor) as cursor:
            # Verify existing check-in
            cursor.execute(
                """SELECT id FROM attendance 
                WHERE username=%s AND DATE(check_in_time)=CURDATE() 
                AND check_out_time IS NULL""",
                (current_user,)
            )
            if not cursor.fetchone():
                return jsonify({'message': 'No active check-in found'}), 400

            # Record check-out
            cursor.execute(
                """UPDATE attendance SET check_out_time=%s 
                WHERE username=%s AND DATE(check_in_time)=CURDATE() 
                AND check_out_time IS NULL""",
                (check_out_time, current_user)
            )
            mysql.connection.commit()

        return jsonify({
            'message': 'Check-out recorded',
            'check_out_time': check_out_time.isoformat()
        })

    except Exception as e:
        logger.error(f"Check-out error: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/attendance/history', methods=['GET'])
@token_required
def attendance_history(current_user: str, is_admin: bool):
    """Get attendance history for the current user"""
    try:
        with mysql.connection.cursor(MySQLdb.cursors.DictCursor) as cursor:
            cursor.execute(
                """SELECT 
                    DATE(check_in_time) as date,
                    MIN(check_in_time) as check_in,
                    MAX(check_out_time) as check_out
                FROM attendance 
                WHERE username=%s
                GROUP BY DATE(check_in_time)
                ORDER BY date DESC
                LIMIT 30""",
                (current_user,)
            )
            records = cursor.fetchall()

        return jsonify({
            'message': 'Attendance history retrieved',
            'data': records
        })

    except Exception as e:
        logger.error(f"History error: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/admin/attendance', methods=['GET'])
@token_required
@admin_required
def admin_attendance(current_user: str, is_admin: bool):
    """Admin endpoint to view all attendance records"""
    try:
        with mysql.connection.cursor(MySQLdb.cursors.DictCursor) as cursor:
            cursor.execute(
                """SELECT 
                    u.username,
                    DATE(a.check_in_time) as date,
                    MIN(a.check_in_time) as check_in,
                    MAX(a.check_out_time) as check_out
                FROM attendance a
                JOIN user u ON a.username = u.username
                GROUP BY u.username, DATE(a.check_in_time)
                ORDER BY date DESC
                LIMIT 100"""
            )
            records = cursor.fetchall()

        return jsonify({
            'message': 'Admin attendance report',
            'data': records
        })

    except Exception as e:
        logger.error(f"Admin report error: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=os.getenv('FLASK_DEBUG', False))
