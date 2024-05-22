import logging
from flask import Flask, jsonify, request, session
from flask_mysqldb import MySQL, MySQLdb
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
from datetime import timedelta, datetime

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'cairocoders-ednalan'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=10)
CORS(app)

# Database configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'yourusername'
app.config['MYSQL_PASSWORD'] = 'yourpassword'
app.config['MYSQL_DB'] = 'testingdb'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
mysql = MySQL(app)

# Setup logging
logging.basicConfig(level=logging.DEBUG)

def is_valid_latitude(latitude):
    return -90 <= latitude <= 90

def is_valid_longitude(longitude):
    return -180 <= longitude <= 180

@app.route('/')
def home():
    if 'username' in session:
        username = session['username']
        return jsonify({'message': 'You are already logged in', 'username': username})
    else:
        resp = jsonify({'message': 'Unauthorized'})
        resp.status_code = 404
        return resp

@app.route('/login', methods=['POST'])
def login():
    try:
        _json = request.json
        _username = _json['username']
        _password = _json['password']

        if _username and _password:
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            sql = "SELECT * FROM user WHERE username=%s"
            cursor.execute(sql, (_username,))
            row = cursor.fetchone()
            if row:
                username = row['username']
                password = row['password']
                is_admin = row['is_admin']
                if check_password_hash(password, _password):
                    session['username'] = username
                    session['is_admin'] = is_admin
                    cursor.close()
                    return jsonify({'message': 'You are logged in successfully'})
                else:
                    resp = jsonify({'message': 'Bad Request - invalid password'})
                    resp.status_code = 400
                    return resp
            else:
                resp = jsonify({'message': 'Bad Request - user not found'})
                resp.status_code = 400
                return resp
        else:
            resp = jsonify({'message': 'Bad Request - invalid credentials'})
            resp.status_code = 400
            return resp
    except Exception as e:
        logging.error(f"Error during login: {str(e)}")
        return jsonify({'message': 'Internal Server Error', 'error': str(e)}), 500

@app.route('/logout')
def logout():
    if 'username' in session:
        session.pop('username', None)
        session.pop('is_admin', None)
        return jsonify({'message': 'You successfully logged out'})
    else:
        return jsonify({'message': 'No active session'}), 400

@app.route('/api/employee/checkin', methods=['POST'])
def checkin():
    if 'username' in session:
        username = session['username']
        _json = request.json
        latitude = _json.get('latitude')
        longitude = _json.get('longitude')

        if not (latitude and longitude):
            return jsonify({'message': 'Bad Request - missing latitude or longitude'}), 400

        if not is_valid_latitude(latitude):
            return jsonify({'message': 'Bad Request - invalid latitude'}), 400

        if not is_valid_longitude(longitude):
            return jsonify({'message': 'Bad Request - invalid longitude'}), 400

        check_in_time = datetime.now()
        if check_in_time > datetime.now():
            return jsonify({'message': 'Bad Request - future check-in time'}), 400

        try:
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            sql = "SELECT * FROM attendance WHERE username=%s AND DATE(check_in_time) = CURDATE()"
            cursor.execute(sql, (username,))
            row = cursor.fetchone()
            if row:
                return jsonify({'message': 'Bad Request - check-in already exists for today'}), 400

            sql = "INSERT INTO attendance (username, check_in_time, latitude, longitude) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (username, check_in_time, latitude, longitude))
            mysql.connection.commit()
            cursor.close()
            return jsonify({'message': 'Check-in successful', 'check_in_time': check_in_time.strftime('%Y-%m-%d %H:%M:%S')})
        except Exception as e:
            logging.error(f"Error during check-in: {str(e)}")
            return jsonify({'message': 'Internal Server Error', 'error': str(e)}), 500
    else:
        return jsonify({'message': 'Unauthorized'}), 404

@app.route('/api/employee/checkout', methods=['POST'])
def checkout():
    if 'username' in session:
        username = session['username']
        check_out_time = datetime.now()
        if check_out_time > datetime.now():
            return jsonify({'message': 'Bad Request - future check-out time'}), 400

        try:
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            sql = "SELECT * FROM attendance WHERE username=%s AND DATE(check_in_time) = CURDATE() AND check_out_time IS NULL"
            cursor.execute(sql, (username,))
            row = cursor.fetchone()
            if not row:
                return jsonify({'message': 'Bad Request - no check-in record found for today'}), 400

            sql = "UPDATE attendance SET check_out_time=%s WHERE username=%s AND check_out_time IS NULL"
            cursor.execute(sql, (check_out_time, username))
            mysql.connection.commit()
            cursor.close()
            return jsonify({'message': 'Check-out successful', 'check_out_time': check_out_time.strftime('%Y-%m-%d %H:%M:%S')})
        except Exception as e:
            logging.error(f"Error during check-out: {str(e)}")
            return jsonify({'message': 'Internal Server Error', 'error': str(e)}), 500
    else:
        return jsonify({'message': 'Unauthorized'}), 404

@app.route('/api/employee/attendance', methods=['GET'])
def employee_attendance():
    if 'username' in session:
        username = session['username']
        try:
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            sql = "SELECT * FROM attendance WHERE username=%s"
            cursor.execute(sql, (username,))
            records = cursor.fetchall()
            cursor.close()
            return jsonify({'message': 'Attendance records fetched successfully', 'records': records})
        except Exception as e:
            logging.error(f"Error fetching attendance records: {str(e)}")
            return jsonify({'message': 'Internal Server Error', 'error': str(e)}), 500
    else:
        return jsonify({'message': 'Unauthorized'}), 404

@app.route('/api/admin/attendance', methods=['GET'])
def admin_attendance():
    if 'username' in session and session.get('is_admin'):
        try:
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            sql = "SELECT * FROM attendance"
            cursor.execute(sql)
            records = cursor.fetchall()
            cursor.close()
            return jsonify({'message': 'All attendance records fetched successfully', 'records': records})
        except Exception as e:
            logging.error(f"Error fetching all attendance records: {str(e)}")
            return jsonify({'message': 'Internal Server Error', 'error': str(e)}), 500
    else:
        return jsonify({'message': 'Unauthorized'}), 404

if __name__ == "__main__":
    app.run(debug=True)
