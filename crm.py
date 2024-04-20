import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import hashlib

# ユーザー認証
def authenticate_user(users):
    user_id = st.sidebar.text_input("ユーザーID")
    password = st.sidebar.text_input("パスワード", type="password")
    if st.sidebar.button("ログイン"):
        if user_id in users and users[user_id] == password:
            st.session_state["user_id"] = user_id
            st.success("ログイン成功")
            return True
        else:
            st.error("ユーザーIDまたはパスワードが間違っています")
            return False
    return False

def create_user_db(user_id):
    db_path = f'data_{user_id}.db'
    conn = sqlite3.connect(db_path, check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS customer_table(
            customer_id TEXT PRIMARY KEY,
            name TEXT UNIQUE,
            birthday DATE,
            age INTEGER,
            occupation TEXT,
            employment_history TEXT,
            place_of_birth TEXT,
            hobbies TEXT,
            family_members TEXT,
            needs TEXT
        )
    ''')
    conn.commit()
    return conn
def get_customer_by_id(conn, customer_id):
    c = conn.cursor()
    c.execute('SELECT * FROM customer_table WHERE customer_id = ?', (customer_id,))
    data = c.fetchone()
    return data if data else None

def update_customer(conn, data):
    with conn:
        conn.execute('''
            UPDATE customer_table
            SET name=:name, birthday=:birthday, age=:age, occupation=:occupation, employment_history=:employment_history, place_of_birth=:place_of_birth, hobbies=:hobbies, family_members=:family_members, needs=:needs
            WHERE customer_id=:customer_id
        ''', data)
        conn.commit()

# その他の関数やmain関数の定義は以前提供したものと同じです。

def add_customer(conn, data):
    try:
        with conn:
            conn.execute('''
                INSERT INTO customer_table (customer_id, name, birthday, age, occupation, employment_history, place_of_birth, hobbies, family_members, needs)
                VALUES (:customer_id, :name, :birthday, :age, :occupation, :employment_history, :place_of_birth, :hobbies, :family_members, :needs)
            ''', data)
            st.success('顧客情報が登録されました。')
    except sqlite3.IntegrityError:
        st.error(f"重複エラー: {data['name']} はすでに登録されています。")

def import_customers(conn, csv_file):
    df = pd.read_csv(csv_file)
    for _, row in df.iterrows():
        birthday = datetime.strptime(row['birthday'], '%Y-%m-%d')
        age = calculate_age(birthday)
        data = {
            'customer_id': hashlib.md5(row['name'].encode()).hexdigest()[:12],
            'name': row['name'],
            'birthday': row['birthday'],
            'age': age,
            'occupation': row['occupation'],
            'employment_history': row['employment_history'],
            'place_of_birth': row['place_of_birth'],
            'hobbies': row['hobbies'],
            'family_members': row['family_members'],
            'needs': row['needs']
        }
        add_customer(conn, data)

def calculate_age(birthday):
    today = datetime.today()
    return today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))

def main():
    st.title('営業管理ツール')

    # ユーザー認証情報
    users = {
        "user1": "password1",
        "user2": "password2"
    }

    if "user_id" not in st.session_state:
        authenticate_user(users)
    if "user_id" in st.session_state:
        conn = create_user_db(st.session_state["user_id"])

        # CSVインポート機能
        st.subheader("CSVから顧客データをインポート")
        csv_file = st.file_uploader("CSVファイルを選択してください", type=["csv"])
        if csv_file and st.button("インポート"):
            import_customers(conn, csv_file)

        # 顧客情報登録
        with st.form("customer_form"):
            st.write("顧客情報登録")
            name = st.text_input("名前")
            birthday = st.date_input("生年月日")
            age = calculate_age(birthday)
            occupation = st.text_input("職種")
            employment_history = st.text_area("職歴")
            place_of_birth = st.text_input("出生地")
            hobbies = st.text_input("趣味")
            family_members = st.text_input("家族構成")
            needs = st.text_area("ニーズ")
            submit_button = st.form_submit_button("登録")
            if submit_button:
                customer_id = hashlib.md5(name.encode()).hexdigest()[:12]
                data = {
                    'customer_id': customer_id,
                    'name': name,
                    'birthday': birthday.strftime('%Y-%m-%d'),
                    'age': age,
                    'occupation': occupation,
                    'employment_history': employment_history,
                    'place_of_birth': place_of_birth,
                    'hobbies': hobbies,
                    'family_members': family_members,
                    'needs': needs
                }
                add_customer(conn, data)

        # 顧客情報一覧と詳細編集
        if st.checkbox('顧客情報一覧を表示'):
            c = conn.cursor()
            c.execute('SELECT * FROM customer_table')
            customer_data = c.fetchall()
            customer_df = pd.DataFrame(customer_data, columns=["ID", "名前", "生年月日", "年齢", "職種", "職歴", "出生地", "趣味", "家族構成", "ニーズ"])
            st.write(customer_df)
            selected_customer_id = st.selectbox('編集する顧客のIDを選択', customer_df['ID'])
            customer_details = get_customer_by_id(conn, selected_customer_id)
            if customer_details:
                with st.form("edit_customer"):
                    name, birthday_str, _, occupation, employment_history, place_of_birth, hobbies, family_members, needs = customer_details[1:]
                    birthday = datetime.strptime(birthday_str, '%Y-%m-%d')
                    age = calculate_age(birthday)
                    st.text_input("名前", value=name, key="name")
                    st.date_input("生年月日", value=birthday, key="birthday")
                    st.text_input("職種", value=occupation, key="occupation")
                    st.text_area("職歴", value=employment_history, key="employment_history")
                    st.text_input("出生地", value=place_of_birth, key="place_of_birth")
                    st.text_input("趣味", value=hobbies, key="hobbies")
                    st.text_input("家族構成", value=family_members, key="family_members")
                    st.text_area("ニーズ", value=needs, key="needs")
                    update_button = st.form_submit_button("更新")
                    if update_button:
                        update_data = {
                            'customer_id': selected_customer_id,
                            'name': st.session_state.name,
                            'birthday': st.session_state.birthday.strftime('%Y-%m-%d'),
                            'age': calculate_age(st.session_state.birthday),
                            'occupation': st.session_state.occupation,
                            'employment_history': st.session_state.employment_history,
                            'place_of_birth': st.session_state.place_of_birth,
                            'hobbies': st.session_state.hobbies,
                            'family_members': st.session_state.family_members,
                            'needs': st.session_state.needs
                        }
                        update_customer(conn, update_data)
                        st.success('顧客情報が更新されました。')

if __name__ == '__main__':
    main()
