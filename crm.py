import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import hashlib
import csv

# データベース接続の設定
conn = sqlite3.connect('customer_data.db', check_same_thread=False)
c = conn.cursor()

def create_table():
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
create_table()

def add_customer(data):
    with conn:
        c.execute('''
            INSERT INTO customer_table (customer_id, name, birthday, age, occupation, employment_history, place_of_birth, hobbies, family_members, needs)
            VALUES (:customer_id, :name, :birthday, :age, :occupation, :employment_history, :place_of_birth, :hobbies, :family_members, :needs)
        ''', data)

def update_customer(data):
    with conn:
        c.execute('''
            UPDATE customer_table
            SET name=:name, birthday=:birthday, age=:age, occupation=:occupation, employment_history=:employment_history, place_of_birth=:place_of_birth, hobbies=:hobbies, family_members=:family_members, needs=:needs
            WHERE customer_id=:customer_id
        ''', data)

def view_all_customers():
    c.execute('SELECT * FROM customer_table')
    data = c.fetchall()
    return data

def get_customer_by_id(customer_id):
    c.execute('SELECT * FROM customer_table WHERE customer_id = ?', (customer_id,))
    data = c.fetchone()
    return data if data else None

def calculate_age(birthday):
    today = datetime.today()
    return today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))

def import_customers(csv_file):
    df = pd.read_csv(csv_file)
    for _, row in df.iterrows():
        birthday = datetime.strptime(row['birthday'], '%Y-%m-%d')
        data = {
            'customer_id': hashlib.md5(row['name'].encode()).hexdigest()[:12],
            'name': row['name'],
            'birthday': row['birthday'],
            'age': calculate_age(birthday),
            'occupation': row['occupation'],
            'employment_history': row['employment_history'],
            'place_of_birth': row['place_of_birth'],
            'hobbies': row['hobbies'],
            'family_members': row['family_members'],
            'needs': row['needs']
        }
        try:
            add_customer(data)
        except sqlite3.IntegrityError:
            st.warning(f"顧客名 {row['name']} は既に登録されています。")

def app():
    st.title('営業管理ツール')

    if "reload" not in st.session_state:
        st.session_state.reload = True

    # 顧客情報登録
    with st.form("customer_form"):
        st.write("顧客情報登録")
        name = st.text_input("名前")
        birthday = st.date_input("生年月日")
        age = calculate_age(birthday)  # 自動計算される年齢
        occupation = st.text_input("職種")
        employment_history = st.text_area("職歴")
        place_of_birth = st.text_input("出生地")
        hobbies = st.text_input("趣味")
        family_members = st.text_input("家族構成")
        needs = st.text_area("ニーズ")
        submit_button = st.form_submit_button("登録")

        if submit_button:
            customer_id = hashlib.md5(name.encode()).hexdigest()[:12]
            add_customer({
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
            })
            st.session_state.reload = True
            st.success('顧客情報が登録されました。')

    # 顧客情報一覧と詳細編集
    if st.checkbox('顧客情報一覧を表示', value=st.session_state.reload):
        customer_data = view_all_customers()
        customer_df = pd.DataFrame(customer_data, columns=["ID", "名前", "生年月日", "年齢", "職種", "職歴", "出生地", "趣味", "家族構成", "ニーズ"])
        st.write(customer_df)
        selected_customer_id = st.selectbox('編集する顧客のIDを選択', customer_df['ID'])
        customer_details = get_customer_by_id(selected_customer_id)
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
                    update_customer(update_data)
                    st.session_state.reload = True
                    st.success('顧客情報が更新されました。')

# CSV インポート機能
    st.subheader("CSVから顧客データをインポート")
    csv_file = st.file_uploader("CSVファイルを選択してください", type=["csv"])
    if st.button("インポート"):
        import_customers(csv_file)
        st.success("顧客データがインポートされました。")

    # サンプルCSVのダウンロード
    st.subheader("サンプルCSVのダウンロード")
    if st.button("サンプルCSVをダウンロード"):
        sample_data = {
            'name': ['山田 太郎', '鈴木 花子'],
            'birthday': ['1980-05-01', '1990-10-15'],
            'occupation': ['会社員', '自由業'],
            'employment_history': ['株式会社A 10年', '株式会社B 5年'],
            'place_of_birth': ['東京', '大阪'],
            'hobbies': ['釣り', '読書'],
            'family_members': ['未婚', '既婚'],
            'needs': ['新製品の情報', '定期的な情報更新']
        }
        df = pd.DataFrame(sample_data)
        csv = df.to_csv(index=False)
        st.download_button(label="ダウンロード", data=csv, file_name='sample_customers.csv', mime='text/csv')


if __name__ == '__main__':
    app()
