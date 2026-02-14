import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
import hashlib
import uuid


# --- データベース ---

def get_connection(user_id):
    db_path = f"data_{user_id}.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            company TEXT,
            birthday DATE,
            age INTEGER,
            occupation TEXT,
            employment_history TEXT,
            place_of_birth TEXT,
            hobbies TEXT,
            family_members TEXT,
            needs TEXT,
            status TEXT DEFAULT '見込み',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            activity_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            description TEXT,
            activity_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
        )
    ''')
    conn.commit()


# --- ユーティリティ ---

def calculate_age(birthday):
    if isinstance(birthday, str):
        birthday = datetime.strptime(birthday, "%Y-%m-%d").date()
    today = date.today()
    return today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))


def generate_id(name):
    return hashlib.md5(f"{name}{uuid.uuid4().hex[:6]}".encode()).hexdigest()[:12]


# --- 認証 ---

USERS = {
    "user1": "password1",
    "user2": "password2",
}


def login_form():
    st.sidebar.header("ログイン")
    user_id = st.sidebar.text_input("ユーザーID")
    password = st.sidebar.text_input("パスワード", type="password")
    if st.sidebar.button("ログイン"):
        if user_id in USERS and USERS[user_id] == password:
            st.session_state["user_id"] = user_id
            st.rerun()
        else:
            st.sidebar.error("ユーザーIDまたはパスワードが間違っています")


def logout_button():
    if st.sidebar.button("ログアウト"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# --- 顧客CRUD ---

def add_customer(conn, data):
    try:
        with conn:
            conn.execute('''
                INSERT INTO customers
                    (customer_id, name, email, phone, company, birthday, age,
                     occupation, employment_history, place_of_birth,
                     hobbies, family_members, needs, status)
                VALUES
                    (:customer_id, :name, :email, :phone, :company, :birthday, :age,
                     :occupation, :employment_history, :place_of_birth,
                     :hobbies, :family_members, :needs, :status)
            ''', data)
        return True
    except sqlite3.IntegrityError:
        return False


def update_customer(conn, data):
    with conn:
        conn.execute('''
            UPDATE customers
            SET name=:name, email=:email, phone=:phone, company=:company,
                birthday=:birthday, age=:age, occupation=:occupation,
                employment_history=:employment_history,
                place_of_birth=:place_of_birth, hobbies=:hobbies,
                family_members=:family_members, needs=:needs, status=:status
            WHERE customer_id=:customer_id
        ''', data)


def delete_customer(conn, customer_id):
    with conn:
        conn.execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,))


def get_all_customers(conn):
    return pd.read_sql_query("SELECT * FROM customers ORDER BY created_at DESC", conn)


def get_customer(conn, customer_id):
    row = conn.execute(
        "SELECT * FROM customers WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM customers LIMIT 0").description]
    return dict(zip(cols, row))


def search_customers(conn, keyword):
    query = """
        SELECT * FROM customers
        WHERE name LIKE ? OR email LIKE ? OR company LIKE ?
              OR phone LIKE ? OR occupation LIKE ? OR needs LIKE ?
        ORDER BY created_at DESC
    """
    like = f"%{keyword}%"
    return pd.read_sql_query(query, conn, params=[like] * 6)


# --- 活動履歴 ---

def add_activity(conn, data):
    with conn:
        conn.execute('''
            INSERT INTO activities (activity_id, customer_id, activity_type, description, activity_date)
            VALUES (:activity_id, :customer_id, :activity_type, :description, :activity_date)
        ''', data)


def get_activities(conn, customer_id):
    return pd.read_sql_query(
        "SELECT * FROM activities WHERE customer_id = ? ORDER BY activity_date DESC",
        conn, params=[customer_id]
    )


def get_recent_activities(conn, limit=10):
    return pd.read_sql_query('''
        SELECT a.activity_date, a.activity_type, a.description, c.name AS customer_name
        FROM activities a
        JOIN customers c ON a.customer_id = c.customer_id
        ORDER BY a.activity_date DESC
        LIMIT ?
    ''', conn, params=[limit])


# --- CSV インポート ---

def import_customers_csv(conn, csv_file):
    df = pd.read_csv(csv_file)
    success, failed = 0, 0
    for _, row in df.iterrows():
        birthday_str = row.get("birthday", "")
        age = 0
        if birthday_str:
            try:
                age = calculate_age(birthday_str)
            except (ValueError, TypeError):
                pass
        data = {
            "customer_id": generate_id(str(row.get("name", ""))),
            "name": str(row.get("name", "")),
            "email": str(row.get("email", "")),
            "phone": str(row.get("phone", "")),
            "company": str(row.get("company", "")),
            "birthday": birthday_str,
            "age": age,
            "occupation": str(row.get("occupation", "")),
            "employment_history": str(row.get("employment_history", "")),
            "place_of_birth": str(row.get("place_of_birth", "")),
            "hobbies": str(row.get("hobbies", "")),
            "family_members": str(row.get("family_members", "")),
            "needs": str(row.get("needs", "")),
            "status": str(row.get("status", "見込み")),
        }
        if add_customer(conn, data):
            success += 1
        else:
            failed += 1
    return success, failed


# --- UI ページ ---

STATUS_OPTIONS = ["見込み", "商談中", "契約済み", "失注", "休眠"]
ACTIVITY_TYPES = ["電話", "メール", "訪問", "会議", "その他"]


def page_dashboard(conn):
    st.header("ダッシュボード")

    df = get_all_customers(conn)
    total = len(df)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("顧客数", total)

    if total > 0:
        status_counts = df["status"].value_counts()
        col2.metric("商談中", int(status_counts.get("商談中", 0)))
        col3.metric("契約済み", int(status_counts.get("契約済み", 0)))
        col4.metric("見込み", int(status_counts.get("見込み", 0)))

        st.subheader("ステータス別分布")
        st.bar_chart(status_counts)
    else:
        col2.metric("商談中", 0)
        col3.metric("契約済み", 0)
        col4.metric("見込み", 0)

    st.subheader("最近の活動")
    recent = get_recent_activities(conn, limit=10)
    if recent.empty:
        st.info("活動履歴はまだありません。")
    else:
        st.dataframe(
            recent.rename(columns={
                "activity_date": "日付",
                "activity_type": "種類",
                "description": "内容",
                "customer_name": "顧客名",
            }),
            use_container_width=True,
            hide_index=True,
        )


def page_customer_list(conn):
    st.header("顧客一覧")

    keyword = st.text_input("検索（名前・メール・会社名・電話・職種・ニーズ）")
    if keyword:
        df = search_customers(conn, keyword)
    else:
        df = get_all_customers(conn)

    if df.empty:
        st.info("顧客データがありません。")
        return

    display_cols = {
        "customer_id": "ID",
        "name": "名前",
        "email": "メール",
        "phone": "電話",
        "company": "会社名",
        "status": "ステータス",
        "occupation": "職種",
    }
    existing_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[existing_cols].rename(columns=display_cols),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"{len(df)} 件の顧客")


def page_customer_register(conn):
    st.header("顧客登録")

    with st.form("register_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("名前 *")
        email = col2.text_input("メールアドレス")
        phone = col1.text_input("電話番号")
        company = col2.text_input("会社名")
        birthday = col1.date_input("生年月日", value=None)
        status = col2.selectbox("ステータス", STATUS_OPTIONS)
        occupation = col1.text_input("職種")
        place_of_birth = col2.text_input("出生地")
        employment_history = st.text_area("職歴")
        hobbies = col1.text_input("趣味")
        family_members = col2.text_input("家族構成")
        needs = st.text_area("ニーズ")

        submitted = st.form_submit_button("登録")
        if submitted:
            if not name:
                st.error("名前は必須です。")
            else:
                age = calculate_age(birthday) if birthday else 0
                data = {
                    "customer_id": generate_id(name),
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "company": company,
                    "birthday": birthday.strftime("%Y-%m-%d") if birthday else "",
                    "age": age,
                    "occupation": occupation,
                    "employment_history": employment_history,
                    "place_of_birth": place_of_birth,
                    "hobbies": hobbies,
                    "family_members": family_members,
                    "needs": needs,
                    "status": status,
                }
                if add_customer(conn, data):
                    st.success(f"顧客「{name}」を登録しました。")
                else:
                    st.error("登録に失敗しました。")


def page_customer_detail(conn):
    st.header("顧客詳細・編集")

    df = get_all_customers(conn)
    if df.empty:
        st.info("顧客データがありません。")
        return

    options = {row["customer_id"]: f"{row['name']}（{row['company'] or '-'}）" for _, row in df.iterrows()}
    selected_id = st.selectbox("顧客を選択", list(options.keys()), format_func=lambda x: options[x])
    cust = get_customer(conn, selected_id)
    if cust is None:
        st.error("顧客が見つかりません。")
        return

    tab_info, tab_activity = st.tabs(["基本情報", "活動履歴"])

    with tab_info:
        with st.form("edit_form"):
            col1, col2 = st.columns(2)
            name = col1.text_input("名前", value=cust["name"])
            email = col2.text_input("メールアドレス", value=cust.get("email", ""))
            phone = col1.text_input("電話番号", value=cust.get("phone", ""))
            company = col2.text_input("会社名", value=cust.get("company", ""))
            bday_val = None
            if cust.get("birthday"):
                try:
                    bday_val = datetime.strptime(cust["birthday"], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    pass
            birthday = col1.date_input("生年月日", value=bday_val)
            current_status = cust.get("status", "見込み")
            idx = STATUS_OPTIONS.index(current_status) if current_status in STATUS_OPTIONS else 0
            status = col2.selectbox("ステータス", STATUS_OPTIONS, index=idx)
            occupation = col1.text_input("職種", value=cust.get("occupation", ""))
            place_of_birth = col2.text_input("出生地", value=cust.get("place_of_birth", ""))
            employment_history = st.text_area("職歴", value=cust.get("employment_history", ""))
            hobbies = col1.text_input("趣味", value=cust.get("hobbies", ""))
            family_members = col2.text_input("家族構成", value=cust.get("family_members", ""))
            needs = st.text_area("ニーズ", value=cust.get("needs", ""))

            col_btn1, col_btn2 = st.columns([1, 1])
            update_btn = col_btn1.form_submit_button("更新")
            if update_btn:
                age = calculate_age(birthday) if birthday else 0
                update_data = {
                    "customer_id": selected_id,
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "company": company,
                    "birthday": birthday.strftime("%Y-%m-%d") if birthday else "",
                    "age": age,
                    "occupation": occupation,
                    "employment_history": employment_history,
                    "place_of_birth": place_of_birth,
                    "hobbies": hobbies,
                    "family_members": family_members,
                    "needs": needs,
                    "status": status,
                }
                update_customer(conn, update_data)
                st.success("顧客情報を更新しました。")

        if st.button("この顧客を削除", type="secondary"):
            delete_customer(conn, selected_id)
            st.success("顧客を削除しました。")
            st.rerun()

    with tab_activity:
        st.subheader("活動履歴")
        activities = get_activities(conn, selected_id)
        if not activities.empty:
            st.dataframe(
                activities[["activity_date", "activity_type", "description"]].rename(columns={
                    "activity_date": "日付",
                    "activity_type": "種類",
                    "description": "内容",
                }),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("活動履歴はまだありません。")

        st.subheader("活動を追加")
        with st.form("add_activity_form", clear_on_submit=True):
            a_col1, a_col2 = st.columns(2)
            activity_type = a_col1.selectbox("種類", ACTIVITY_TYPES)
            activity_date = a_col2.date_input("日付", value=date.today())
            description = st.text_area("内容")
            if st.form_submit_button("追加"):
                if not description:
                    st.error("内容を入力してください。")
                else:
                    add_activity(conn, {
                        "activity_id": uuid.uuid4().hex[:12],
                        "customer_id": selected_id,
                        "activity_type": activity_type,
                        "description": description,
                        "activity_date": activity_date.strftime("%Y-%m-%d"),
                    })
                    st.success("活動を追加しました。")
                    st.rerun()


def page_import(conn):
    st.header("CSVインポート")

    st.markdown("""
CSVファイルから顧客データを一括インポートできます。

**必須カラム:** `name`

**対応カラム:** `email`, `phone`, `company`, `birthday`, `occupation`,
`employment_history`, `place_of_birth`, `hobbies`, `family_members`, `needs`, `status`
    """)

    csv_file = st.file_uploader("CSVファイルを選択", type=["csv"])
    if csv_file and st.button("インポート実行"):
        success, failed = import_customers_csv(conn, csv_file)
        if success:
            st.success(f"{success} 件の顧客をインポートしました。")
        if failed:
            st.warning(f"{failed} 件の顧客のインポートに失敗しました（重複など）。")


# --- メインアプリ ---

def main():
    st.set_page_config(page_title="営業CRM", page_icon="📋", layout="wide")
    st.title("営業CRM")

    if "user_id" not in st.session_state:
        login_form()
        st.info("サイドバーからログインしてください。")
        return

    conn = get_connection(st.session_state["user_id"])
    init_db(conn)

    st.sidebar.markdown(f"**ログインユーザー:** {st.session_state['user_id']}")
    logout_button()

    st.sidebar.divider()
    page = st.sidebar.radio(
        "メニュー",
        ["ダッシュボード", "顧客一覧", "顧客登録", "顧客詳細・編集", "CSVインポート"],
    )

    if page == "ダッシュボード":
        page_dashboard(conn)
    elif page == "顧客一覧":
        page_customer_list(conn)
    elif page == "顧客登録":
        page_customer_register(conn)
    elif page == "顧客詳細・編集":
        page_customer_detail(conn)
    elif page == "CSVインポート":
        page_import(conn)


if __name__ == "__main__":
    main()
