import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date, timedelta
import hashlib
import uuid
import io


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
    c.execute('''
        CREATE TABLE IF NOT EXISTS deals (
            deal_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            title TEXT NOT NULL,
            amount REAL DEFAULT 0,
            stage TEXT DEFAULT '初期接触',
            probability INTEGER DEFAULT 10,
            expected_close_date DATE,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            customer_id TEXT,
            deal_id TEXT,
            title TEXT NOT NULL,
            description TEXT,
            due_date DATE,
            priority TEXT DEFAULT '中',
            is_completed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE SET NULL,
            FOREIGN KEY (deal_id) REFERENCES deals(deal_id) ON DELETE SET NULL
        )
    ''')
    conn.commit()


# --- ユーティリティ ---

def calculate_age(birthday):
    if isinstance(birthday, str):
        birthday = datetime.strptime(birthday, "%Y-%m-%d").date()
    today = date.today()
    return today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))


def generate_id(name=""):
    return hashlib.md5(f"{name}{uuid.uuid4().hex[:8]}".encode()).hexdigest()[:12]


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


# --- 商談（Deal）管理 ---

DEAL_STAGES = ["初期接触", "ヒアリング", "提案", "見積提出", "交渉", "受注", "失注"]
DEAL_STAGE_PROB = {"初期接触": 10, "ヒアリング": 25, "提案": 40, "見積提出": 60, "交渉": 80, "受注": 100, "失注": 0}


def add_deal(conn, data):
    with conn:
        conn.execute('''
            INSERT INTO deals (deal_id, customer_id, title, amount, stage, probability, expected_close_date, description)
            VALUES (:deal_id, :customer_id, :title, :amount, :stage, :probability, :expected_close_date, :description)
        ''', data)


def update_deal(conn, data):
    with conn:
        conn.execute('''
            UPDATE deals
            SET title=:title, amount=:amount, stage=:stage, probability=:probability,
                expected_close_date=:expected_close_date, description=:description,
                closed_at=:closed_at
            WHERE deal_id=:deal_id
        ''', data)


def delete_deal(conn, deal_id):
    with conn:
        conn.execute("DELETE FROM deals WHERE deal_id = ?", (deal_id,))


def get_all_deals(conn):
    return pd.read_sql_query('''
        SELECT d.*, c.name AS customer_name
        FROM deals d
        JOIN customers c ON d.customer_id = c.customer_id
        ORDER BY d.created_at DESC
    ''', conn)


def get_deals_by_customer(conn, customer_id):
    return pd.read_sql_query(
        "SELECT * FROM deals WHERE customer_id = ? ORDER BY created_at DESC",
        conn, params=[customer_id]
    )


def get_deal(conn, deal_id):
    row = conn.execute("SELECT * FROM deals WHERE deal_id = ?", (deal_id,)).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM deals LIMIT 0").description]
    return dict(zip(cols, row))


# --- タスク管理 ---

PRIORITY_OPTIONS = ["高", "中", "低"]


def add_task(conn, data):
    with conn:
        conn.execute('''
            INSERT INTO tasks (task_id, customer_id, deal_id, title, description, due_date, priority)
            VALUES (:task_id, :customer_id, :deal_id, :title, :description, :due_date, :priority)
        ''', data)


def update_task_status(conn, task_id, is_completed):
    completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if is_completed else None
    with conn:
        conn.execute(
            "UPDATE tasks SET is_completed = ?, completed_at = ? WHERE task_id = ?",
            (int(is_completed), completed_at, task_id)
        )


def delete_task(conn, task_id):
    with conn:
        conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))


def get_all_tasks(conn, include_completed=False):
    if include_completed:
        query = '''
            SELECT t.*, c.name AS customer_name, d.title AS deal_title
            FROM tasks t
            LEFT JOIN customers c ON t.customer_id = c.customer_id
            LEFT JOIN deals d ON t.deal_id = d.deal_id
            ORDER BY t.is_completed ASC, t.due_date ASC
        '''
    else:
        query = '''
            SELECT t.*, c.name AS customer_name, d.title AS deal_title
            FROM tasks t
            LEFT JOIN customers c ON t.customer_id = c.customer_id
            LEFT JOIN deals d ON t.deal_id = d.deal_id
            WHERE t.is_completed = 0
            ORDER BY t.due_date ASC
        '''
    return pd.read_sql_query(query, conn)


def get_overdue_tasks(conn):
    today = date.today().strftime("%Y-%m-%d")
    return pd.read_sql_query('''
        SELECT t.*, c.name AS customer_name
        FROM tasks t
        LEFT JOIN customers c ON t.customer_id = c.customer_id
        WHERE t.is_completed = 0 AND t.due_date < ?
        ORDER BY t.due_date ASC
    ''', conn, params=[today])


def get_upcoming_tasks(conn, days=7):
    today = date.today().strftime("%Y-%m-%d")
    future = (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")
    return pd.read_sql_query('''
        SELECT t.*, c.name AS customer_name
        FROM tasks t
        LEFT JOIN customers c ON t.customer_id = c.customer_id
        WHERE t.is_completed = 0 AND t.due_date >= ? AND t.due_date <= ?
        ORDER BY t.due_date ASC
    ''', conn, params=[today, future])


# --- CSV インポート/エクスポート ---

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


def export_customers_csv(conn):
    df = get_all_customers(conn)
    if df.empty:
        return None
    export_cols = ["name", "email", "phone", "company", "birthday", "occupation",
                   "employment_history", "place_of_birth", "hobbies", "family_members", "needs", "status"]
    existing = [c for c in export_cols if c in df.columns]
    return df[existing].to_csv(index=False).encode("utf-8-sig")


def export_deals_csv(conn):
    df = get_all_deals(conn)
    if df.empty:
        return None
    export_cols = ["customer_name", "title", "amount", "stage", "probability", "expected_close_date", "description"]
    existing = [c for c in export_cols if c in df.columns]
    return df[existing].to_csv(index=False).encode("utf-8-sig")


# --- UI ページ ---

STATUS_OPTIONS = ["見込み", "商談中", "契約済み", "失注", "休眠"]
ACTIVITY_TYPES = ["電話", "メール", "訪問", "会議", "その他"]


def page_dashboard(conn):
    st.header("ダッシュボード")

    customers_df = get_all_customers(conn)
    deals_df = get_all_deals(conn)
    overdue = get_overdue_tasks(conn)
    upcoming = get_upcoming_tasks(conn, days=7)

    total_customers = len(customers_df)

    # KPI行1: 顧客
    st.subheader("顧客サマリー")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("総顧客数", total_customers)
    if total_customers > 0:
        status_counts = customers_df["status"].value_counts()
        c2.metric("商談中", int(status_counts.get("商談中", 0)))
        c3.metric("契約済み", int(status_counts.get("契約済み", 0)))
        c4.metric("見込み", int(status_counts.get("見込み", 0)))
    else:
        c2.metric("商談中", 0)
        c3.metric("契約済み", 0)
        c4.metric("見込み", 0)

    # KPI行2: 商談
    st.subheader("商談サマリー")
    d1, d2, d3, d4 = st.columns(4)
    if not deals_df.empty:
        active_deals = deals_df[~deals_df["stage"].isin(["受注", "失注"])]
        won_deals = deals_df[deals_df["stage"] == "受注"]
        d1.metric("進行中の商談", len(active_deals))
        d2.metric("進行中の合計金額", f"¥{active_deals['amount'].sum():,.0f}")
        d3.metric("受注済み", len(won_deals))
        d4.metric("受注合計金額", f"¥{won_deals['amount'].sum():,.0f}")
    else:
        d1.metric("進行中の商談", 0)
        d2.metric("進行中の合計金額", "¥0")
        d3.metric("受注済み", 0)
        d4.metric("受注合計金額", "¥0")

    # タスクアラート
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("期限切れタスク")
        if overdue.empty:
            st.success("期限切れのタスクはありません。")
        else:
            st.error(f"{len(overdue)} 件の期限切れタスクがあります")
            for _, t in overdue.iterrows():
                cname = t.get("customer_name", "-") or "-"
                st.markdown(f"- **{t['title']}**（{cname}）期限: {t['due_date']}")

    with col_right:
        st.subheader("今後7日のタスク")
        if upcoming.empty:
            st.info("直近のタスクはありません。")
        else:
            for _, t in upcoming.iterrows():
                cname = t.get("customer_name", "-") or "-"
                st.markdown(f"- **{t['title']}**（{cname}）期限: {t['due_date']}")

    # 商談パイプライン
    if not deals_df.empty:
        st.subheader("商談パイプライン")
        active_deals = deals_df[~deals_df["stage"].isin(["受注", "失注"])]
        if not active_deals.empty:
            pipeline = active_deals.groupby("stage")["amount"].agg(["sum", "count"]).reset_index()
            pipeline.columns = ["ステージ", "合計金額", "件数"]
            stage_order = [s for s in DEAL_STAGES if s not in ["受注", "失注"]]
            pipeline["sort_key"] = pipeline["ステージ"].apply(lambda x: stage_order.index(x) if x in stage_order else 99)
            pipeline = pipeline.sort_values("sort_key").drop(columns=["sort_key"])
            st.dataframe(pipeline, use_container_width=True, hide_index=True)

    # ステータス分布
    if total_customers > 0:
        st.subheader("顧客ステータス分布")
        status_counts = customers_df["status"].value_counts()
        st.bar_chart(status_counts)

    # 最近の活動
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

    col_search, col_filter = st.columns([3, 1])
    keyword = col_search.text_input("検索（名前・メール・会社名・電話・職種・ニーズ）")
    status_filter = col_filter.selectbox("ステータスで絞込", ["すべて"] + STATUS_OPTIONS)

    if keyword:
        df = search_customers(conn, keyword)
    else:
        df = get_all_customers(conn)

    if status_filter != "すべて" and not df.empty:
        df = df[df["status"] == status_filter]

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

    tab_info, tab_activity, tab_deals = st.tabs(["基本情報", "活動履歴", "商談"])

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

            update_btn = st.form_submit_button("更新")
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

    with tab_deals:
        st.subheader("この顧客の商談")
        cust_deals = get_deals_by_customer(conn, selected_id)
        if not cust_deals.empty:
            for _, d in cust_deals.iterrows():
                stage_icon = "🟢" if d["stage"] == "受注" else ("🔴" if d["stage"] == "失注" else "🔵")
                st.markdown(f"{stage_icon} **{d['title']}** — ¥{d['amount']:,.0f} ／ {d['stage']}（確度 {d['probability']}%）")
        else:
            st.info("この顧客の商談はまだありません。")

        st.subheader("商談を追加")
        with st.form("add_deal_from_detail", clear_on_submit=True):
            dc1, dc2 = st.columns(2)
            deal_title = dc1.text_input("商談名 *")
            deal_amount = dc2.number_input("金額（円）", min_value=0, value=0, step=10000)
            deal_stage = dc1.selectbox("ステージ", DEAL_STAGES)
            deal_prob = dc2.number_input("確度（%）", min_value=0, max_value=100, value=DEAL_STAGE_PROB.get(deal_stage, 10))
            deal_close = dc1.date_input("受注予定日", value=date.today() + timedelta(days=30))
            deal_desc = st.text_area("概要")
            if st.form_submit_button("商談を追加"):
                if not deal_title:
                    st.error("商談名は必須です。")
                else:
                    add_deal(conn, {
                        "deal_id": generate_id(deal_title),
                        "customer_id": selected_id,
                        "title": deal_title,
                        "amount": deal_amount,
                        "stage": deal_stage,
                        "probability": deal_prob,
                        "expected_close_date": deal_close.strftime("%Y-%m-%d"),
                        "description": deal_desc,
                    })
                    st.success("商談を追加しました。")
                    st.rerun()


def page_deals(conn):
    st.header("商談管理")

    deals_df = get_all_deals(conn)

    if deals_df.empty:
        st.info("商談データがありません。顧客詳細ページから商談を追加してください。")
        return

    # パイプラインビュー
    st.subheader("パイプライン")
    active_stages = [s for s in DEAL_STAGES if s not in ["受注", "失注"]]
    cols = st.columns(len(active_stages))
    for i, stage in enumerate(active_stages):
        stage_deals = deals_df[deals_df["stage"] == stage]
        with cols[i]:
            total = stage_deals["amount"].sum()
            st.markdown(f"**{stage}**")
            st.caption(f"{len(stage_deals)} 件 ／ ¥{total:,.0f}")
            for _, d in stage_deals.iterrows():
                st.markdown(f"- {d['customer_name']}: **{d['title']}** ¥{d['amount']:,.0f}")

    st.divider()

    # 商談一覧テーブル
    st.subheader("全商談一覧")
    stage_filter = st.selectbox("ステージで絞込", ["すべて"] + DEAL_STAGES)
    filtered = deals_df if stage_filter == "すべて" else deals_df[deals_df["stage"] == stage_filter]

    if filtered.empty:
        st.info("該当する商談がありません。")
    else:
        display = filtered[["customer_name", "title", "amount", "stage", "probability", "expected_close_date"]].copy()
        display.columns = ["顧客名", "商談名", "金額", "ステージ", "確度（%）", "受注予定日"]
        st.dataframe(display, use_container_width=True, hide_index=True)

    # 商談編集
    st.divider()
    st.subheader("商談の編集")
    deal_options = {row["deal_id"]: f"{row['customer_name']} - {row['title']}" for _, row in deals_df.iterrows()}
    selected_deal_id = st.selectbox("商談を選択", list(deal_options.keys()), format_func=lambda x: deal_options[x])
    deal = get_deal(conn, selected_deal_id)
    if deal:
        with st.form("edit_deal_form"):
            ec1, ec2 = st.columns(2)
            e_title = ec1.text_input("商談名", value=deal["title"])
            e_amount = ec2.number_input("金額（円）", min_value=0, value=int(deal["amount"]), step=10000)
            current_stage_idx = DEAL_STAGES.index(deal["stage"]) if deal["stage"] in DEAL_STAGES else 0
            e_stage = ec1.selectbox("ステージ", DEAL_STAGES, index=current_stage_idx)
            e_prob = ec2.number_input("確度（%）", min_value=0, max_value=100, value=int(deal["probability"]))
            close_val = None
            if deal.get("expected_close_date"):
                try:
                    close_val = datetime.strptime(deal["expected_close_date"], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    pass
            e_close = ec1.date_input("受注予定日", value=close_val)
            e_desc = st.text_area("概要", value=deal.get("description", ""))

            if st.form_submit_button("更新"):
                closed_at = None
                if e_stage in ["受注", "失注"] and deal["stage"] not in ["受注", "失注"]:
                    closed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                update_deal(conn, {
                    "deal_id": selected_deal_id,
                    "title": e_title,
                    "amount": e_amount,
                    "stage": e_stage,
                    "probability": e_prob,
                    "expected_close_date": e_close.strftime("%Y-%m-%d") if e_close else "",
                    "description": e_desc,
                    "closed_at": closed_at or deal.get("closed_at"),
                })
                st.success("商談を更新しました。")
                st.rerun()

        if st.button("この商談を削除", type="secondary"):
            delete_deal(conn, selected_deal_id)
            st.success("商談を削除しました。")
            st.rerun()


def page_tasks(conn):
    st.header("タスク管理")

    show_completed = st.checkbox("完了済みも表示")
    tasks_df = get_all_tasks(conn, include_completed=show_completed)

    if tasks_df.empty:
        st.info("タスクがありません。")
    else:
        today_str = date.today().strftime("%Y-%m-%d")
        for _, t in tasks_df.iterrows():
            is_done = bool(t["is_completed"])
            is_overdue = not is_done and t.get("due_date") and str(t["due_date"]) < today_str

            prefix = "~~" if is_done else ""
            suffix = "~~" if is_done else ""
            priority_icon = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(t["priority"], "⚪")
            overdue_tag = " **[期限切れ]**" if is_overdue else ""

            cname = t.get("customer_name", "") or ""
            dname = t.get("deal_title", "") or ""
            context = f"（{cname}{'／' + dname if dname else ''}）" if cname else ""

            col_check, col_text, col_del = st.columns([0.5, 8, 1])
            with col_check:
                new_state = st.checkbox("完了", value=is_done, key=f"task_{t['task_id']}", label_visibility="collapsed")
                if new_state != is_done:
                    update_task_status(conn, t["task_id"], new_state)
                    st.rerun()
            with col_text:
                st.markdown(f"{priority_icon} {prefix}**{t['title']}**{suffix}{context} — 期限: {t.get('due_date', '-')}{overdue_tag}")
            with col_del:
                if st.button("削除", key=f"del_task_{t['task_id']}"):
                    delete_task(conn, t["task_id"])
                    st.rerun()

    # タスク追加
    st.divider()
    st.subheader("タスクを追加")
    customers_df = get_all_customers(conn)
    customer_map = {"（なし）": None}
    for _, row in customers_df.iterrows():
        customer_map[f"{row['name']}（{row['company'] or '-'}）"] = row["customer_id"]

    deals_df = get_all_deals(conn)
    deal_map = {"（なし）": None}
    for _, row in deals_df.iterrows():
        deal_map[f"{row['customer_name']} - {row['title']}"] = row["deal_id"]

    with st.form("add_task_form", clear_on_submit=True):
        tc1, tc2 = st.columns(2)
        task_title = tc1.text_input("タスク名 *")
        task_priority = tc2.selectbox("優先度", PRIORITY_OPTIONS, index=1)
        task_due = tc1.date_input("期限", value=date.today() + timedelta(days=3))
        task_customer = tc2.selectbox("関連顧客", list(customer_map.keys()))
        task_deal = tc1.selectbox("関連商談", list(deal_map.keys()))
        task_desc = st.text_area("詳細")
        if st.form_submit_button("追加"):
            if not task_title:
                st.error("タスク名は必須です。")
            else:
                add_task(conn, {
                    "task_id": generate_id(task_title),
                    "customer_id": customer_map[task_customer],
                    "deal_id": deal_map[task_deal],
                    "title": task_title,
                    "description": task_desc,
                    "due_date": task_due.strftime("%Y-%m-%d"),
                    "priority": task_priority,
                })
                st.success("タスクを追加しました。")
                st.rerun()


def page_analytics(conn):
    st.header("分析・レポート")

    deals_df = get_all_deals(conn)
    customers_df = get_all_customers(conn)

    if deals_df.empty and customers_df.empty:
        st.info("データがまだありません。")
        return

    # 商談分析
    if not deals_df.empty:
        st.subheader("商談分析")

        won = deals_df[deals_df["stage"] == "受注"]
        lost = deals_df[deals_df["stage"] == "失注"]
        active = deals_df[~deals_df["stage"].isin(["受注", "失注"])]

        m1, m2, m3, m4 = st.columns(4)
        total_deals = len(deals_df)
        m1.metric("総商談数", total_deals)
        m2.metric("受注率", f"{len(won)/total_deals*100:.1f}%" if total_deals > 0 else "0%")
        m3.metric("平均商談金額", f"¥{deals_df['amount'].mean():,.0f}" if total_deals > 0 else "¥0")
        m4.metric("加重パイプライン", f"¥{(active['amount'] * active['probability'] / 100).sum():,.0f}" if not active.empty else "¥0")

        # ステージ別分布
        st.subheader("ステージ別商談件数")
        stage_counts = deals_df["stage"].value_counts()
        st.bar_chart(stage_counts)

        # ステージ別金額
        st.subheader("ステージ別合計金額")
        stage_amounts = deals_df.groupby("stage")["amount"].sum()
        st.bar_chart(stage_amounts)

        # 月別受注推移
        if not won.empty and "closed_at" in won.columns:
            won_with_date = won.dropna(subset=["closed_at"])
            if not won_with_date.empty:
                st.subheader("月別受注金額推移")
                won_with_date = won_with_date.copy()
                won_with_date["closed_month"] = pd.to_datetime(won_with_date["closed_at"]).dt.to_period("M").astype(str)
                monthly = won_with_date.groupby("closed_month")["amount"].sum()
                st.bar_chart(monthly)

        # 顧客別商談金額TOP
        st.subheader("顧客別商談金額TOP10")
        cust_totals = deals_df.groupby("customer_name")["amount"].sum().sort_values(ascending=False).head(10)
        st.bar_chart(cust_totals)

    # 顧客分析
    if not customers_df.empty:
        st.subheader("顧客分析")

        st.markdown("**ステータス分布**")
        status_counts = customers_df["status"].value_counts()
        st.bar_chart(status_counts)

        if "occupation" in customers_df.columns:
            occ = customers_df["occupation"].dropna()
            occ = occ[occ != ""]
            if not occ.empty:
                st.markdown("**職種別分布TOP10**")
                occ_counts = occ.value_counts().head(10)
                st.bar_chart(occ_counts)

        if "company" in customers_df.columns:
            comp = customers_df["company"].dropna()
            comp = comp[comp != ""]
            if not comp.empty:
                st.markdown("**会社別顧客数TOP10**")
                comp_counts = comp.value_counts().head(10)
                st.bar_chart(comp_counts)


def page_import_export(conn):
    st.header("データ管理")

    tab_import, tab_export = st.tabs(["インポート", "エクスポート"])

    with tab_import:
        st.subheader("CSVインポート")
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

    with tab_export:
        st.subheader("CSVエクスポート")

        st.markdown("**顧客データ**")
        csv_customers = export_customers_csv(conn)
        if csv_customers:
            st.download_button(
                "顧客データをダウンロード",
                csv_customers,
                file_name=f"customers_{date.today().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("エクスポートする顧客データがありません。")

        st.markdown("**商談データ**")
        csv_deals = export_deals_csv(conn)
        if csv_deals:
            st.download_button(
                "商談データをダウンロード",
                csv_deals,
                file_name=f"deals_{date.today().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("エクスポートする商談データがありません。")


# --- メインアプリ ---

MENU_ITEMS = [
    "ダッシュボード",
    "顧客一覧",
    "顧客登録",
    "顧客詳細・編集",
    "商談管理",
    "タスク管理",
    "分析・レポート",
    "データ管理",
]


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
    page = st.sidebar.radio("メニュー", MENU_ITEMS)

    if page == "ダッシュボード":
        page_dashboard(conn)
    elif page == "顧客一覧":
        page_customer_list(conn)
    elif page == "顧客登録":
        page_customer_register(conn)
    elif page == "顧客詳細・編集":
        page_customer_detail(conn)
    elif page == "商談管理":
        page_deals(conn)
    elif page == "タスク管理":
        page_tasks(conn)
    elif page == "分析・レポート":
        page_analytics(conn)
    elif page == "データ管理":
        page_import_export(conn)


if __name__ == "__main__":
    main()
