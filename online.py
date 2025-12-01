import streamlit as st
import mysql.connector
from mysql.connector import Error
import hashlib
import pandas as pd
from datetime import datetime

# try optional fallback driver
try:
    import pymysql
except Exception:
    pymysql = None

# Connection wrapper so existing code can call conn.cursor(dictionary=True)
class _ConnWrapper:
    def __init__(self, conn, is_pymysql=False):
        self._conn = conn
        self._is_pymysql = is_pymysql

    def cursor(self, dictionary=False):
        if self._is_pymysql:
            # return a PyMySQL DictCursor when dictionary=True
            return self._conn.cursor(pymysql.cursors.DictCursor if dictionary else None)
        else:
            return self._conn.cursor(dictionary=dictionary)

    def commit(self):
        return self._conn.commit()

    def close(self):
        return self._conn.close()

# Safe rerun helper (works across Streamlit versions)
def safe_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()
    else:
        # As a last resort stop execution and ask user to refresh
        st.stop()

# Database connection
def create_connection():
    """Try mysql-connector (with mysql_native_password). If it fails due to
    caching_sha2_password, fall back to PyMySQL (install with `pip install PyMySQL`)."""
    try:
        conn = mysql.connector.connect(
            host='localhost',
            database='online_exam',
            user='root',
            password='juned6504',
            auth_plugin='mysql_native_password',
            use_pure=True
        )
        return _ConnWrapper(conn, is_pymysql=False)
    except Exception as e:
        err = str(e)
        # If connector doesn't support caching_sha2_password try PyMySQL fallback
        if ('caching_sha2_password' in err or 'Authentication plugin' in err) and pymysql:
            try:
                pconn = pymysql.connect(
                    host='localhost',
                    user='root',
                    password='juned6504',
                    db='online_exam',
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=False
                )
                return _ConnWrapper(pconn, is_pymysql=True)
            except Exception as e2:
                st.error(f"Fallback PyMySQL connection failed: {e2}")
                return None
        else:
            st.error(f"Error connecting to MySQL: {e}")
            return None

# Initialize database tables
def init_database():
    conn = create_connection()
    if conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                user_type ENUM('admin', 'student') NOT NULL,
                full_name VARCHAR(255),
                email VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Ensure legacy tables get new columns if they were created before the email/full_name fields existed
        cursor.execute("SHOW COLUMNS FROM users LIKE 'email'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE users ADD COLUMN email VARCHAR(255)")
        cursor.execute("SHOW COLUMNS FROM users LIKE 'full_name'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE users ADD COLUMN full_name VARCHAR(255)")
        
        # Create default admin user
        admin_password = hash_password('jnx@6504')
        cursor.execute("""
            INSERT IGNORE INTO users (username, password, user_type, full_name)
            VALUES ('admin', %s, 'admin', 'Administrator')
        """, (admin_password,))
        
        # Exams table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id INT AUTO_INCREMENT PRIMARY KEY,
                exam_name VARCHAR(255) NOT NULL,
                duration_minutes INT NOT NULL,
                total_marks INT NOT NULL,
                created_by INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        
        # Questions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                exam_id INT NOT NULL,
                question_text TEXT NOT NULL,
                option_a VARCHAR(255) NOT NULL,
                option_b VARCHAR(255) NOT NULL,
                option_c VARCHAR(255) NOT NULL,
                option_d VARCHAR(255) NOT NULL,
                correct_answer ENUM('A', 'B', 'C', 'D') NOT NULL,
                marks INT DEFAULT 1,
                FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
            )
        """)
        
        # Results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                exam_id INT NOT NULL,
                score INT NOT NULL,
                total_marks INT NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id),
                FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()
        cursor.close()
        conn.close()

# Hash password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Authentication
def authenticate(username, password, user_type):
    conn = create_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        hashed_pw = hash_password(password)
        cursor.execute(
            "SELECT * FROM users WHERE username=%s AND password=%s AND user_type=%s",
            (username, hashed_pw, user_type)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        return user
    return None

# Student Registration
def register_student(username, password, full_name, email):
    conn = create_connection()
    if conn:
        cursor = conn.cursor()
        try:
            hashed_pw = hash_password(password)
            cursor.execute(
                "INSERT INTO users (username, password, user_type, full_name, email) VALUES (%s, %s, 'student', %s, %s)",
                (username, hashed_pw, full_name, email)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Error as e:
            st.error(f"Registration failed: {e}")
            return False
    return False

# Admin Functions
def create_exam(exam_name, duration, total_marks, admin_id):
    conn = create_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO exams (exam_name, duration_minutes, total_marks, created_by) VALUES (%s, %s, %s, %s)",
            (exam_name, duration, total_marks, admin_id)
        )
        exam_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()
        return exam_id
    return None

def add_question(exam_id, question, opt_a, opt_b, opt_c, opt_d, correct, marks):
    conn = create_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO questions (exam_id, question_text, option_a, option_b, 
               option_c, option_d, correct_answer, marks) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (exam_id, question, opt_a, opt_b, opt_c, opt_d, correct, marks)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    return False

def delete_exam(exam_id):
    conn = create_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM exams WHERE id=%s", (exam_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    return False

def get_all_exams():
    conn = create_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM exams ORDER BY created_at DESC")
        exams = cursor.fetchall()
        cursor.close()
        conn.close()
        return exams
    return []

def get_exam_questions(exam_id):
    conn = create_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,))
        questions = cursor.fetchall()
        cursor.close()
        conn.close()
        return questions
    return []

def get_all_results():
    conn = create_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT r.*, u.full_name, u.username, e.exam_name 
            FROM results r
            JOIN users u ON r.student_id = u.id
            JOIN exams e ON r.exam_id = e.id
            ORDER BY r.submitted_at DESC
        """)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    return []

# Student Functions
def submit_exam(student_id, exam_id, score, total_marks):
    conn = create_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO results (student_id, exam_id, score, total_marks) VALUES (%s, %s, %s, %s)",
            (student_id, exam_id, score, total_marks)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    return False

def get_student_results(student_id):
    conn = create_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT r.*, e.exam_name 
            FROM results r
            JOIN exams e ON r.exam_id = e.id
            WHERE r.student_id = %s
            ORDER BY r.submitted_at DESC
        """, (student_id,))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    return []

def check_exam_taken(student_id, exam_id):
    conn = create_connection()
    if conn:
        cursor = conn.cursor()
        # return a named column so dict-cursors have a predictable key
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM results WHERE student_id=%s AND exam_id=%s",
            (student_id, exam_id)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if not row:
            return False
        # handle both dict (PyMySQL / dict-cursor) and tuple results
        if isinstance(row, dict):
            count = row.get('cnt', None)
            if count is None:
                # fallback to first value
                count = next(iter(row.values()))
        else:
            count = row[0]
        try:
            return int(count) > 0
        except Exception:
            return False
    return False

# Initialize session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_type' not in st.session_state:
    st.session_state.user_type = None
if 'user_data' not in st.session_state:
    st.session_state.user_data = None
if 'question_list' not in st.session_state:
    st.session_state.question_list = []

# Initialize database
init_database()

# Main App
def main():
    st.set_page_config(page_title="Online Examination System", layout="wide")
    
    if not st.session_state.logged_in:
        login_page()
    else:
        if st.session_state.user_type == 'admin':
            admin_interface()
        else:
            student_interface()

def login_page():
    st.title("🎓 Online Examination System")
    st.markdown("---")
    
    # Add a reset button to clear session-state if needed
    if st.button("Reset session"):
        for k in ['logged_in', 'user_type', 'user_data', 'exam_started', 'current_exam', 'current_exam_id', 'question_list']:
            if k in st.session_state:
                del st.session_state[k]
        safe_rerun()
    
    # Create tabs for login and registration
    tab1, tab2, tab3 = st.tabs(["👨‍💼 Admin Login", "🎓 Student Login", "📝 Student Registration"])
        
    with tab1:
        st.subheader("Admin Login")
        with st.form("admin_login_form"):
            admin_user = st.text_input("Username", key="admin_user")
            admin_pass = st.text_input("Password", type="password", key="admin_pass")
            admin_login_btn = st.form_submit_button("🔐 Login as Admin", use_container_width=True)
            
            if admin_login_btn:
                user = authenticate(admin_user, admin_pass, 'admin')
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user_type = 'admin'
                    st.session_state.user_data = user
                    st.rerun()
                else:
                    st.error("❌ Invalid credentials!")
    
    with tab2:
        st.subheader("Student Login")
        st.info("💡 Don't have an account? Register in the **Student Registration** tab!")
        
        with st.form("student_login_form"):
            student_user = st.text_input("Username", key="student_user")
            student_pass = st.text_input("Password", type="password", key="student_pass")
            student_login_btn = st.form_submit_button("🔐 Login as Student", use_container_width=True)
            
            if student_login_btn:
                user = authenticate(student_user, student_pass, 'student')
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user_type = 'student'
                    st.session_state.user_data = user
                    st.rerun()
                else:
                    st.error("❌ Invalid credentials! Please check your username and password.")
    
    with tab3:
        st.subheader("Create Your Student Account")
        st.info("📝 Fill in the details below to register as a student")
        
        with st.form("registration_form"):
            reg_full_name = st.text_input("Full Name *", placeholder="Enter your full name", key="reg_full_name")
            reg_email = st.text_input("Email *", placeholder="your.email@example.com", key="reg_email")
            reg_username = st.text_input("Username *", placeholder="Choose a username", key="reg_username")
            
            col1, col2 = st.columns(2)
            with col1:
                reg_password = st.text_input("Password *", type="password", placeholder="Min 6 characters", key="reg_password")
            with col2:
                reg_confirm_password = st.text_input("Confirm Password *", type="password", placeholder="Re-enter password", key="reg_confirm_password")
            
            st.caption("* All fields are required")
            register_btn = st.form_submit_button("✅ Register Now", use_container_width=True, type="primary")
            
            if register_btn:
                if not reg_full_name or not reg_username or not reg_password or not reg_email:
                    st.error("❌ Please fill all fields!")
                elif reg_password != reg_confirm_password:
                    st.error("❌ Passwords do not match!")
                elif len(reg_password) < 6:
                    st.error("❌ Password must be at least 6 characters long!")
                elif '@' not in reg_email:
                    st.error("❌ Please enter a valid email address!")
                else:
                    if register_student(reg_username, reg_password, reg_full_name, reg_email):
                        st.success("🎉 Registration successful! You can now login from the **Student Login** tab.")
                        st.balloons()
                    else:
                        st.error("❌ Registration failed! Username might already exist.")

def admin_interface():
    st.title("👨‍💼 Admin Dashboard")
    st.write(f"Welcome, {st.session_state.user_data['full_name']}!")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user_type = None
        st.session_state.user_data = None
        st.session_state.question_list = []
        st.rerun()
    
    menu = st.sidebar.radio("Menu", ["Create Exam", "View Exams", "View Results"])
    
    if menu == "Create Exam":
        st.header("Create New Exam")
        
        # Exam creation form
        with st.form("exam_form"):
            exam_name = st.text_input("Exam Name")
            col1, col2 = st.columns(2)
            with col1:
                duration = st.number_input("Duration (minutes)", min_value=1, value=60)
            with col2:
                total_marks = st.number_input("Total Marks", min_value=1, value=100)
            
            submit_exam = st.form_submit_button("Create Exam")
            
            if submit_exam:
                if exam_name:
                    exam_id = create_exam(exam_name, duration, total_marks, st.session_state.user_data['id'])
                    if exam_id:
                        st.success(f"✅ Exam created successfully! Exam ID: {exam_id}")
                        st.session_state.current_exam_id = exam_id
                        st.session_state.question_list = []
                else:
                    st.error("Please enter exam name!")
        
        # Multiple questions addition
        if 'current_exam_id' in st.session_state:
            st.divider()
            st.subheader(f"📝 Add Questions to Exam (ID: {st.session_state.current_exam_id})")
            
            # Display added questions count
            existing_questions = get_exam_questions(st.session_state.current_exam_id)
            st.info(f"Total questions added: {len(existing_questions)}")
            
            with st.form("question_form", clear_on_submit=True):
                question = st.text_area("Question Text", height=100)
                
                col1, col2 = st.columns(2)
                with col1:
                    opt_a = st.text_input("Option A")
                    opt_c = st.text_input("Option C")
                with col2:
                    opt_b = st.text_input("Option B")
                    opt_d = st.text_input("Option D")
                
                col1, col2 = st.columns(2)
                with col1:
                    correct = st.selectbox("Correct Answer", ["A", "B", "C", "D"])
                with col2:
                    marks = st.number_input("Marks", min_value=1, value=1)
                
                col1, col2 = st.columns(2)
                with col1:
                    add_question_btn = st.form_submit_button("➕ Add Question", type="primary")
                with col2:
                    finish_exam_btn = st.form_submit_button("✅ Finish Exam", type="secondary")
                
                if add_question_btn:
                    if question and opt_a and opt_b and opt_c and opt_d:
                        if add_question(st.session_state.current_exam_id, question, opt_a, opt_b, opt_c, opt_d, correct, marks):
                            st.success("✅ Question added successfully! You can add more questions.")
                            st.rerun()
                        else:
                            st.error("Failed to add question!")
                    else:
                        st.error("Please fill all question fields!")
                
                if finish_exam_btn:
                    if len(existing_questions) > 0:
                        st.success(f"🎉 Exam completed with {len(existing_questions)} questions!")
                        del st.session_state.current_exam_id
                        st.rerun()
                    else:
                        st.error("Please add at least one question before finishing!")
            
            # Show added questions
            if existing_questions:
                st.divider()
                st.subheader("Added Questions Preview")
                for i, q in enumerate(existing_questions, 1):
                    with st.expander(f"Question {i}: {q['question_text'][:50]}..."):
                        st.markdown(f"**{q['question_text']}** ({q['marks']} marks)")
                        st.write(f"A) {q['option_a']}")
                        st.write(f"B) {q['option_b']}")
                        st.write(f"C) {q['option_c']}")
                        st.write(f"D) {q['option_d']}")
                        st.success(f"✅ Correct Answer: {q['correct_answer']}")
    
    elif menu == "View Exams":
        st.header("All Exams")
        exams = get_all_exams()
        
        if exams:
            for exam in exams:
                with st.expander(f"📝 {exam['exam_name']} - {exam['duration_minutes']} mins"):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"**Total Marks:** {exam['total_marks']}")
                        st.write(f"**Created:** {exam['created_at']}")
                    
                    questions = get_exam_questions(exam['id'])
                    st.write(f"**Number of Questions:** {len(questions)}")
                    
                    st.divider()
                    for i, q in enumerate(questions, 1):
                        st.markdown(f"**Q{i}. {q['question_text']}** ({q['marks']} marks)")
                        st.write(f"A) {q['option_a']}")
                        st.write(f"B) {q['option_b']}")
                        st.write(f"C) {q['option_c']}")
                        st.write(f"D) {q['option_d']}")
                        st.write(f"✅ Correct: {q['correct_answer']}")
                        st.divider()
                    
                    if st.button(f"🗑️ Delete Exam", key=f"del_{exam['id']}"):
                        if delete_exam(exam['id']):
                            st.success("Exam deleted!")
                            st.rerun()
        else:
            st.info("No exams created yet!")
    
    elif menu == "View Results":
        st.header("All Student Results")
        results = get_all_results()
        
        if results:
            df = pd.DataFrame(results)
            df = df[['full_name', 'username', 'exam_name', 'score', 'total_marks', 'submitted_at']]
            df['percentage'] = (df['score'] / df['total_marks'] * 100).round(2)
            st.dataframe(df, use_container_width=True)
            
            # Statistics
            st.subheader("📊 Statistics")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Submissions", len(df))
            with col2:
                st.metric("Average Score", f"{df['percentage'].mean():.2f}%")
            with col3:
                st.metric("Highest Score", f"{df['percentage'].max():.2f}%")
        else:
            st.info("No results yet!")

def student_interface():
    st.title("🎓 Student Dashboard")
    st.write(f"Welcome, {st.session_state.user_data['full_name']}!")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user_type = None
        st.session_state.user_data = None
        st.rerun()
    
    menu = st.sidebar.radio("Menu", ["Take Exam", "My Results"])
    
    if menu == "Take Exam":
        st.header("Available Exams")
        exams = get_all_exams()
        
        if exams:
            for exam in exams:
                questions = get_exam_questions(exam['id'])
                exam_taken = check_exam_taken(st.session_state.user_data['id'], exam['id'])
                
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.subheader(exam['exam_name'])
                        st.write(f"⏱️ Duration: {exam['duration_minutes']} minutes | 📊 Total Marks: {exam['total_marks']} | 📝 Questions: {len(questions)}")
                    with col2:
                        if exam_taken:
                            st.success("✅ Completed")
                    with col3:
                        if not exam_taken and len(questions) > 0:
                            if st.button("Start Exam", key=f"start_{exam['id']}"):
                                st.session_state.exam_started = True
                                st.session_state.current_exam = exam
                                st.rerun()
                        elif len(questions) == 0:
                            st.warning("No questions")
                    
                    st.divider()
        else:
            st.info("No exams available!")
        
        # Exam interface
        if 'exam_started' in st.session_state and st.session_state.exam_started:
            exam = st.session_state.current_exam
            questions = get_exam_questions(exam['id'])
            
            st.divider()
            st.header(f"📝 {exam['exam_name']}")
            st.info(f"⏱️ Time: {exam['duration_minutes']} mins | 📊 Total Marks: {exam['total_marks']} | 📝 Questions: {len(questions)}")
            st.divider()
            
            answers = {}
            for i, q in enumerate(questions):
                st.markdown(f"### Question {i+1} ({q['marks']} marks)")
                st.markdown(f"**{q['question_text']}**")
                
                answers[q['id']] = st.radio(
                    f"Select your answer:",
                    ["A", "B", "C", "D"],
                    key=f"q_{q['id']}",
                    format_func=lambda x, q=q: f"{x}) {q[f'option_{x.lower()}']}"
                )
                st.divider()
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                if st.button("📤 Submit Exam", type="primary", use_container_width=True):
                    score = 0
                    for q in questions:
                        if answers[q['id']] == q['correct_answer']:
                            score += q['marks']
                    
                    if submit_exam(st.session_state.user_data['id'], exam['id'], score, exam['total_marks']):
                        percentage = (score / exam['total_marks']) * 100
                        st.success(f"🎉 Exam submitted successfully!")
                        st.balloons()
                        st.metric("Your Score", f"{score}/{exam['total_marks']}", f"{percentage:.2f}%")
                        st.session_state.exam_started = False
                        del st.session_state.current_exam
                        st.rerun()
                    else:
                        st.error("Failed to submit exam!")
    
    elif menu == "My Results":
        st.header("My Exam Results")
        results = get_student_results(st.session_state.user_data['id'])
        
        if results:
            for result in results:
                percentage = (result['score'] / result['total_marks']) * 100
                
                # Determine grade and color
                if percentage >= 90:
                    grade = "A+"
                    color = "green"
                elif percentage >= 80:
                    grade = "A"
                    color = "blue"
                elif percentage >= 70:
                    grade = "B"
                    color = "orange"
                elif percentage >= 60:
                    grade = "C"
                    color = "yellow"
                else:
                    grade = "F"
                    color = "red"
                
                with st.container():
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.subheader(result['exam_name'])
                        st.caption(f"Submitted: {result['submitted_at']}")
                    with col2:
                        st.metric("Score", f"{result['score']}/{result['total_marks']}")
                    with col3:
                        st.metric("Grade", grade, f"{percentage:.1f}%")
                    
                    st.divider()
        else:
            st.info("You haven't taken any exams yet!")

if __name__ == "__main__":
    main()