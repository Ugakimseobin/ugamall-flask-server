from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from flask_babel import Babel
from flask_login import UserMixin
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
import requests
import os
import random, time
from datetime import datetime
from zoneinfo import ZoneInfo
from flask_migrate import Migrate
from sqlalchemy.dialects.mysql import JSON
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
import uuid
from datetime import timedelta

app = Flask(__name__)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

login_manager = LoginManager(app)
login_manager.login_view = "login"  # 로그인 안 된 상태에서 접근 시 이동할 뷰

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

#app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:ugahan582818@localhost:3306/ugamall'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL").replace("postgres://", "postgresql://")

# 안정성 옵션(아이들 타임아웃 대비)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 280
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'ugamall_secret_key'

app.config['BABEL_DEFAULT_LOCALE'] = 'ko'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'

app.config["IMP_CODE"]   = os.getenv("IMP_CODE",   "imp84085058")  # 아임포트 가맹점 코드
app.config["IMP_KEY"]    = os.getenv("IMP_KEY",    "5725674101821141")
app.config["IMP_SECRET"] = os.getenv("IMP_SECRET", "fmHPJ9V9k8TkXerskLSMd4byOKJp13IGYBoL849Y4HtLnDX2oYlrzuLTZaW0geEddnrZHAYBUEl5hVqY")

db = SQLAlchemy(app)
migrate = Migrate(app, db)
# ----------------------------
# 비밀번호 찾기 - 이메일 전송
# ----------------------------
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='fkemfem85@gmail.com',
    MAIL_PASSWORD='grte qfgm qfmf ihia',  # Gmail 앱 비밀번호
    MAIL_DEFAULT_SENDER='fkemfem85l@gmail.com'
)

mail = Mail(app)
s = URLSafeTimedSerializer(app.secret_key)


# ----------------------------

KST = ZoneInfo("Asia/Seoul")

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_PAMPHLET_EXT = {".pdf", ".jpg", ".jpeg", ".png"}

# -----------------------------
# DB 모델
# -----------------------------
class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(50))
    base_address = db.Column(db.String(200))   # 기본주소
    detail_address = db.Column(db.String(200)) # 상세주소
    phone = db.Column(db.String(20))
    phone_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)  # ✅ 관리자 여부 추가
    # 약관 동의
    agree_terms = db.Column(db.Boolean, default=False)          # 유가몰 이용약관
    agree_finance = db.Column(db.Boolean, default=False)        # 전자금융서비스
    agree_privacy = db.Column(db.Boolean, default=False)        # 개인정보수집
    agree_age = db.Column(db.Boolean, default=False)            # 만 14세 이상
    agree_marketing = db.Column(db.Boolean, default=False)      # 마케팅 수신 동의
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(KST))   # 가입일
    last_login = db.Column(db.DateTime(timezone=True), nullable=True)        # 마지막 로그인
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(KST),
                           onupdate=lambda: datetime.now(KST))               # 수정일
    status = db.Column(db.String(20), default="active")  

class Product(db.Model):
    __tablename__ = "product"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    base_price = db.Column(db.Float, nullable=False, default=0)
    description = db.Column(db.Text)
    image = db.Column(db.String(255))
    category = db.Column(db.String(50))
    pamphlet = db.Column(db.String(255))

    product_options = db.relationship("ProductOption", back_populates="product", cascade="all, delete-orphan")
    variants = db.relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")
    cart_items = db.relationship("CartItem", back_populates="product", cascade="all, delete-orphan")


class ProductOption(db.Model):
    __tablename__ = "product_options"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)   # ex) 사이즈, 색상
    value = db.Column(db.String(120), nullable=False)  # ex) 250, 파랑

    product = db.relationship("Product", back_populates="product_options")

class ProductVariant(db.Model):
    __tablename__ = "product_variants"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    sku = db.Column(db.String(100), unique=True)
    price = db.Column(db.Float, nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    options = db.Column(JSON, nullable=False)  # {"사이즈": "250", "색상": "파랑"}

    product = db.relationship("Product", back_populates="variants")
    order_items = db.relationship("OrderItem", back_populates="variant")
    # ✅ cart_items 관계는 단방향으로만 사용 (필요하다면 backref 사용)
    cart_items = db.relationship("CartItem", back_populates="variant", cascade="all, delete-orphan")


class Video(db.Model):
    __tablename__ = 'video'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    file_path = db.Column(db.String(200))

class Inquiry(db.Model):
    __tablename__ = "inquiries"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # 회원
    guest_email = db.Column(db.String(120), nullable=True)  # 비회원 이메일

    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="답변 대기")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    answer = db.Column(db.Text, nullable=True)
    answered_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref="inquiries")

class CartItem(db.Model):
    __tablename__ = "cart_items"
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # 회원일 경우
    session_id = db.Column(db.String(128), nullable=True)  # 비회원용 세션 ID

    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=True)
    quantity = db.Column(db.Integer, default=1)

    user = db.relationship("User", backref="cart_items")
    product = db.relationship("Product", back_populates="cart_items")
    variant = db.relationship("ProductVariant", back_populates="cart_items")

class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    merchant_uid = db.Column(db.String(100), unique=True, index=True)  # 우리 주문 고유번호
    imp_uid = db.Column(db.String(100), index=True)                    # 아임포트 결제 고유 ID
    amount = db.Column(db.Integer, nullable=False)                      # 결제 금액(원)
    method = db.Column(db.String(30))                                   # card, vbank 등
    status = db.Column(db.String(20), default="ready")                  # ready, paid, failed, cancelled
    pg_provider = db.Column(db.String(50))
    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship("Order", back_populates="payment")

class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)

    # ✅ 회원 주문 (user_id) / 비회원 주문 (guest_email)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    guest_email = db.Column(db.String(120), nullable=True)   # 비회원 이메일 저장

    name = db.Column(db.String(100), nullable=False)   # 주문자 이름
    phone = db.Column(db.String(20), nullable=False)   # 주문자 전화번호
    base_address = db.Column(db.String(200), nullable=False)
    detail_address = db.Column(db.String(200), nullable=True)  # 배송 주소
    payment_method = db.Column(db.String(50), nullable=False)  # 카드, vbank 등
    status = db.Column(db.String(20), default="주문 접수")  # 주문 상태
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 관계
    user = db.relationship("User", backref="orders")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payment = db.relationship("Payment", back_populates="order", uselist=False)


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, nullable=False)

    order = db.relationship("Order", back_populates="items")
    variant = db.relationship("ProductVariant", back_populates="order_items")

# -----------------------------
# 사용자 함수
# -----------------------------
@app.template_filter("sum")
def sum_filter(items, attribute=None):
    if not items:
        return 0
    if attribute:
        return sum(getattr(i, attribute) for i in items)
    return sum(items)

@app.template_filter("won")
def won(n):
    """정수/실수를 1,234 형태 문자열로. 값이 없거나 형변환 실패해도 안전."""
    try:
        if n is None:
            return "0"
        # 소수/문자도 들어올 수 있으니 float→int로 정규화
        return f"{int(float(n)):,}"
    except Exception:
        return "0"

def allowed_file_ext(filename, allowed_exts):
    _, ext = os.path.splitext(filename or "")
    return ext.lower() in allowed_exts and len(ext) > 0

def save_uploaded_file(file_obj, subfolder, allowed_exts):
    """
    파일 저장 후 저장된 파일명 반환.
    - file_obj: Werkzeug FileStorage (request.files['...'])
    - subfolder: 'images' 또는 'pamphlets' 등 (relative to static/)
    - allowed_exts: set of allowed extensions (with dot), e.g. {'.jpg', '.png'}
    """
    if not file_obj or not file_obj.filename:
        return None

    if not allowed_file_ext(file_obj.filename, allowed_exts):
        return None

    # 확장자 추출
    _, ext = os.path.splitext(file_obj.filename)
    ext = ext.lower()

    # 랜덤 파일명 (충돌 확률 거의 0)
    new_filename = f"{uuid.uuid4().hex}{ext}"

    # 저장 경로 (앱 루트/static/<subfolder>)
    static_dir = os.path.join(current_app.root_path, "static")
    dest_dir = os.path.join(static_dir, subfolder)
    os.makedirs(dest_dir, exist_ok=True)  # 디렉토리 없으면 생성

    save_path = os.path.join(dest_dir, new_filename)
    file_obj.save(save_path)

    return new_filename

@app.template_filter("comma")
def comma(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return "0"
# ----------------------------
def select_locale():
    return session.get("lang", "ko")

babel = Babel(app, locale_selector=select_locale)

# ✅ Jinja에서 get_locale()을 쓸 수 있게 context processor 등록
@app.context_processor
def inject_get_locale():
    return {"get_locale": select_locale}
# ----------------------------
#-----------------------------
def _get_iamport_token():
    r = requests.post("https://api.iamport.kr/users/getToken", data={
        "imp_key": app.config["IMP_KEY"],
        "imp_secret": app.config["IMP_SECRET"],
    }, timeout=7)
    r.raise_for_status()
    data = r.json()
    return data["response"]["access_token"]

def cancel_portone_payment(imp_uid, amount=None, reason="관리자 취소",
                           refund_bank=None, refund_account=None, refund_holder=None):
    """
    포트원 결제취소 요청.
    - imp_uid: 결제 고유번호
    - amount: 부분취소 금액(없으면 전액취소)
    - 가상계좌 '입금 후' 환불 시 refund_* 3개 필요 (은행코드는 포트원 코드표)
    """
    token = _get_iamport_token()
    payload = {
        "reason": reason,
        "imp_uid": imp_uid
    }
    if amount:
        payload["amount"] = int(amount)

    # 가상계좌(입금 후 취소)일 때만 필요
    if refund_bank and refund_account and refund_holder:
        payload.update({
            "refund_holder": refund_holder,
            "refund_bank": refund_bank,       # 예: 004(국민), 088(신한), 020(우리) 등
            "refund_account": refund_account
        })

    r = requests.post(
        "https://api.iamport.kr/payments/cancel",
        headers={"Authorization": token},
        data=payload,
        timeout=10
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code", 0) != 0:
        # 포트원 실패 메시지를 그대로 띄우면 원인 파악이 쉬움
        raise RuntimeError(data.get("message", "PG 취소 실패"))

    return data["response"]

def _cart_items_for_current_user():
    if current_user.is_authenticated:
        return CartItem.query.filter_by(user_id=current_user.id).all(), current_user.id, None
    # 비회원용 세션 카트
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    session_id = session["session_id"]
    return CartItem.query.filter_by(session_id=session_id).all(), None, session_id

def _order_sum(order: "Order") -> int:
    return sum(int(i.price) * int(i.quantity) for i in order.items)
#-----------------------------

# -----------------------------
# 주문 상태 한국어 변환
# -----------------------------
STATUS_LABEL_TEXT = {
    "pending":   "결제대기",
    "ready":     "결제대기",
    "paid":      "결제완료",
    "shipped":   "배송중",
    "delivered": "배송완료",
    "canceled":  "취소됨",
    "cancelled": "취소됨",  # 철자 혼용 보정
    "-":         "-",
    None:        "-"
}

# 드롭다운 옵션(변경용)
STATUS_OPTIONS = [
    {"value": "pending",   "label": "결제대기"},
    {"value": "paid",      "label": "결제완료"},
    {"value": "shipped",   "label": "배송중"},
    {"value": "delivered", "label": "배송완료"},
    {"value": "canceled",  "label": "취소됨"},
]

@app.template_filter("status_label")
def status_label(value):
    return STATUS_LABEL_TEXT.get(value, value)

# -----------------------------
# 라우트
# -----------------------------
@app.route('/')
def home():
    latest_video = Video.query.order_by(Video.id.desc()).first()
    products = Product.query.limit(6).all()
    return render_template('index.html', latest_video=latest_video, products=products)

@app.route('/set_lang/<lang>')
def set_lang(lang):
    session['lang'] = lang
    return redirect(request.referrer or url_for('home'))

@app.route("/debug_lang")
def debug_lang():
    return f"Current lang = {session.get('lang')}"

# 1단계: 약관 동의
@app.route("/register/terms", methods=["GET", "POST"])
def register_terms():
    if request.method == "POST":
        required = ["agree_terms", "agree_finance", "agree_privacy", "agree_age"]
        for field in required:
            if field not in request.form:
                flash("필수 약관에 모두 동의해야 합니다.", "error")
                return redirect(url_for("register_terms"))

        # 세션에 약관 동의 정보 저장 (2단계에서 DB에 최종 저장)
        session["agreements"] = {k: (k in request.form) for k in request.form.keys()}
        return redirect(url_for("register_info"))

    return render_template("auth/register_terms.html")


# 2단계: 유저 정보 입력
@app.route("/register/info", methods=["GET", "POST"])
def register_info():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        password_confirm = request.form["password_confirm"]
        name = request.form["name"]
        base_address = request.form["address"]
        detail_address = request.form["detail_address"]
        phone = request.form["phone"]

        # ✅ 이메일 중복 체크
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("이미 사용 중인 이메일입니다.", "error")
            return redirect(url_for("register_info"))
        
        if password != password_confirm:
            flash("비밀번호가 일치하지 않습니다.", "error")
            return redirect(url_for("register_info"))
        
        if not session.get("phone_verified"):
            flash("휴대폰 인증을 완료해야 회원가입이 가능합니다.", "error")
            return redirect(url_for("register_info"))

        user = User(
            email=email,
            name=name,
            base_address=base_address,
            detail_address=detail_address,
            phone=phone,
            last_login=datetime.now(KST),
            agree_terms=session.get("agreements", {}).get("agree_terms", False),
            agree_finance=session.get("agreements", {}).get("agree_finance", False),
            agree_privacy=session.get("agreements", {}).get("agree_privacy", False),
            agree_age=session.get("agreements", {}).get("agree_age", False),
            agree_marketing=session.get("agreements", {}).get("agree_marketing", False),
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("회원가입 완료! 로그인해주세요.", "success")
        return redirect(url_for("login"))

    return render_template("auth/register_info.html")

@app.route("/guest_orders", methods=["GET", "POST"])
def guest_orders():
    if request.method == "POST":
        email = request.form.get("email")
        order_id = request.form.get("order_id")  # 선택 입력

        query = Order.query.filter_by(guest_email=email)

        if order_id:
            query = query.filter_by(id=order_id)

        orders = query.all()
        if not orders:
            flash("주문 내역이 없습니다.", "error")
            return redirect(url_for("guest_orders"))

        return render_template("guest_orders.html", orders=orders, email=email)

    return render_template("guest_orders_search.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)  # ✅ Flask-Login 사용
            user.last_login = datetime.now(KST)
            if user.status == "dormant":
                user.status = "active"
            db.session.commit()

            flash("로그인 성공!", "success")
            return redirect(url_for("home"))
        else:
            flash("이메일 또는 비밀번호가 올바르지 않습니다.", "error")

    return render_template("auth/login.html")

@app.route("/logout")
def logout():
    logout_user()   # ✅ 세션/쿠키 정리
    flash("로그아웃되었습니다.", "success")
    return redirect(url_for("home"))

# ----------------------------------
# SMS 인증 테스트
# ----------------------------------
@app.route("/send_verification_code", methods=["POST"])
def send_verification_code():
    phone = request.form.get("phone")
    if not phone:
        return jsonify({"status": "error", "message": "휴대폰 번호가 필요합니다."})

    # ✅ 6자리 랜덤 인증번호 생성
    code = str(random.randint(100000, 999999))

    # 세션에 저장 (나중엔 DB 테이블로 옮기는게 더 안전)
    session["verification_code"] = code
    session["verification_expiry"] = int(time.time()) + 300  # 5분 유효

    # 테스트용: 콘솔 출력
    print(f"[DEBUG] {phone} 로 발송된 인증번호: {code}")

    # 추후: 여기서 NCP SMS API 호출로 교체 가능
    return jsonify({"status": "ok", "message": "인증번호가 발송되었습니다. (테스트용 콘솔 확인)"})

# 인증번호 확인
@app.route("/verify_code", methods=["POST"])
def verify_code():
    code = request.form.get("code")
    saved_code = session.get("verification_code")
    expiry = session.get("verification_expiry", 0)

    if not saved_code:
        return jsonify({"status": "error", "message": "발송된 인증번호가 없습니다."})

    if int(time.time()) > expiry:
        return jsonify({"status": "error", "message": "인증번호가 만료되었습니다."})

    if code == saved_code:
        session.pop("verification_code", None)
        session.pop("verification_expiry", None)
        session["phone_verified"] = True  # ✅ 인증 완료 플래그
        return jsonify({"status": "ok", "message": "인증 성공!"})

    return jsonify({"status": "error", "message": "인증번호가 올바르지 않습니다."})

@app.route("/mypage", methods=["GET", "POST"])
@login_required   # ✅ Flask-Login 데코레이터 사용
def mypage():
    user = current_user

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "info":
            user.name = request.form.get("name")
            user.base_address = request.form.get("base_address", "")
            user.detail_address = request.form.get("detail_address", "")
            user.agree_marketing = "agree_marketing" in request.form
            db.session.commit()
            flash("개인정보가 수정되었습니다.", "success")

        elif form_type == "password":
            current_pw = request.form.get("current_password")
            new_pw = request.form.get("new_password")
            new_pw_confirm = request.form.get("new_password_confirm")

            if not user.check_password(current_pw):
                flash("현재 비밀번호가 올바르지 않습니다.", "error")
            elif new_pw != new_pw_confirm:
                flash("새 비밀번호가 일치하지 않습니다.", "error")
            else:
                user.set_password(new_pw)
                db.session.commit()
                flash("비밀번호가 변경되었습니다.", "success")

        return redirect(url_for("mypage"))

    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    inquiries = Inquiry.query.filter_by(user_id=user.id).order_by(Inquiry.created_at.desc()).all()

    return render_template("mypage.html", user=user, orders=orders, inquiries=inquiries)

@app.route("/mypage/inquiries")
@login_required
def my_inquiries():
    inquiries = Inquiry.query.filter_by(user_id=current_user.id).order_by(Inquiry.created_at.desc()).all()
    return render_template("mypage.html", inquiries=inquiries, orders=[], user=current_user)

@app.route("/reset_password", methods=["GET", "POST"])
def reset_password_request():
    if request.method == "POST":
        email = request.form["email"]
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("해당 이메일로 가입된 계정이 없습니다.", "error")
            return redirect(url_for("reset_password_request"))

        # 토큰 생성
        token = s.dumps(email, salt="password-reset")
        reset_url = url_for("reset_password_token", token=token, _external=True)

        # 메일 발송
        msg = Message("비밀번호 재설정 안내", recipients=[email])
        msg.body = f"""
        안녕하세요.

        비밀번호를 재설정하려면 아래 링크를 클릭해주세요.
        이 링크는 1시간 동안만 유효합니다.

        {reset_url}

        감사합니다.
        """
        mail.send(msg)

        flash("비밀번호 재설정 메일을 보냈습니다. 메일함을 확인해주세요.", "info")
        return redirect(url_for("login"))

    return render_template("auth/reset_password_request.html")

@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password_token(token):
    try:
        email = s.loads(token, salt="password-reset", max_age=3600)  # 1시간 유효
    except:
        flash("토큰이 만료되었거나 잘못된 요청입니다.", "error")
        return redirect(url_for("reset_password_request"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("유효하지 않은 사용자입니다.", "error")
        return redirect(url_for("reset_password_request"))

    if request.method == "POST":
        new_password = request.form["new_password"]
        new_password_confirm = request.form["new_password_confirm"]

        if new_password != new_password_confirm:
            flash("새 비밀번호가 일치하지 않습니다.", "error")
            return redirect(url_for("reset_password_token", token=token))

        user.set_password(new_password)
        db.session.commit()
        flash("비밀번호가 재설정되었습니다. 로그인 해주세요.", "success")
        return redirect(url_for("login"))

    return render_template("auth/reset_password_form.html")


@app.route('/videos')
def videos():
    all_videos = Video.query.order_by(Video.id.desc()).all()
    return render_template('videos.html', videos=all_videos)

@app.route('/products')
def products():
    name = request.args.get("name","")
    category = request.args.get("category","")
    price_min = request.args.get("price_min",0,type=int)
    price_max = request.args.get("price_max",9999999,type=int)
    query = Product.query
    if name:
        query = query.filter(Product.name.contains(name))
    if category:
        query = query.filter(Product.category == category)
    query = query.filter(Product.base_price >= price_min, Product.base_price <= price_max)
    products = query.all()
    categories = [c[0] for c in db.session.query(Product.category).distinct()]
    return render_template("products.html", products=products, categories=categories)

@app.route('/products/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)

    # 같은 카테고리의 다른 상품 추천 (자기 자신 제외)
    related_products = Product.query.filter(
        Product.category == product.category,
        Product.id != product.id
    ).limit(4).all()

    option_keys = []
    if product.variants:
        first_variant = product.variants[0]
        option_keys = list(first_variant.options.keys())

    return render_template("product_detail.html", product=product, related_products=related_products, option_keys=option_keys)

import json

@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    product_id = request.form.get("product_id")
    quantity = int(request.form.get("quantity", 1))

    if not product_id:
        return jsonify({"status": "error", "message": "상품 ID가 누락되었습니다."}), 400
    
    # 옵션 선택값 모으기
    chosen_options = {k.replace("option_", ""): str(v) for k, v in request.form.items() if k.startswith("option_")}
    chosen_options_str = json.dumps(chosen_options, ensure_ascii=False, sort_keys=True)
    print("프론트에서 선택한 옵션:", chosen_options)

    # ✅ 항상 key 정렬된 JSON 문자열로 변환
    chosen_options_str = json.dumps(chosen_options, ensure_ascii=False, sort_keys=True)

    if current_user.is_authenticated:
        user_id = current_user.id
        session_id = None
    else:
        if "session_id" not in session:
            session["session_id"] = str(uuid.uuid4())
        user_id = None
        session_id = session["session_id"]

    # 해당 옵션 조합 찾기
    variants = ProductVariant.query.filter_by(product_id=product_id).all()
    variant = None
    for v in variants:
        # DB 값도 모두 문자열화해서 비교
        db_options = {k: str(vv) for k, vv in v.options.items()}
        db_options_str = json.dumps(db_options, ensure_ascii=False, sort_keys=True)
        if db_options_str == chosen_options_str:
            variant = v
            break

    if not variant:
        print("❌ 옵션 매칭 실패:", chosen_options, "vs", [v.options for v in variants])
        return jsonify({"status": "error", "message": "해당 옵션 조합이 존재하지 않습니다."})

    if variant.stock < quantity:
        return jsonify({"status": "error", "message": "재고가 부족합니다."})

    cart_item = CartItem(
        user_id=user_id,
        session_id=session_id,
        product_id=product_id,
        variant_id=variant.id,
        quantity=quantity
    )
    db.session.add(cart_item)
    db.session.commit()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"status": "ok", "message": "장바구니에 담겼습니다."})

    flash("장바구니에 담겼습니다.", "success")
    return redirect(url_for("checkout"))


import json

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if current_user.is_authenticated:
        base_q = CartItem.query.filter_by(user_id=current_user.id)
        user_id = current_user.id
    else:
        if "session_id" not in session:
            session["session_id"] = str(uuid.uuid4())
        base_q = CartItem.query.filter_by(session_id=session["session_id"])
        user_id = None

    if request.method == "POST":
        # 구매자 정보
        name = (request.form.get("name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        base_address = (request.form.get("address") or "").strip()
        detail_address = (request.form.get("detail_address") or "").strip()
        payment_method = (request.form.get("payment_method") or "카드결제").strip()

        if not base_address:
            flash("기본 주소를 입력해주세요.", "error")
            return redirect(url_for("checkout"))

        # 비회원 이메일 필수
        guest_email = None
        if not user_id:
            guest_email = (request.form.get("email") or "").strip()
            if not guest_email:
                flash("비회원은 이메일을 입력해야 합니다.", "error")
                return redirect(url_for("checkout"))

        # 체크된 장바구니만 모으기
        selected_ids = request.form.getlist("selected_items")
        if not selected_ids:
            flash("구매할 상품을 선택해주세요.", "error")
            return redirect(url_for("checkout"))

        cart_items = base_q.filter(CartItem.id.in_(selected_ids)).all()
        if not cart_items:
            flash("선택된 장바구니 상품이 없습니다.", "error")
            return redirect(url_for("checkout"))

        # (선택) 체크아웃 화면에서 사용자가 바꾼 수량 반영
        for ci in cart_items:
            raw = request.form.get(f"quantity_{ci.id}")
            if raw:
                try:
                    ci.quantity = max(1, int(raw))
                except ValueError:
                    ci.quantity = 1
        db.session.flush()

        # 주문 생성
        new_order = Order(
            user_id=current_user.id if current_user.is_authenticated else None,
            guest_email=guest_email if not current_user.is_authenticated else None,
            name=name,
            phone=phone,
            base_address=base_address,
            detail_address=detail_address,
            payment_method=payment_method,
            status="주문 접수",
            created_at=datetime.now(KST)
        )
        db.session.add(new_order)
        db.session.flush()  # new_order.id 확보

        # 주문 아이템 생성 + 장바구니 제거
        for item in cart_items:
            unit_price = (item.product.base_price or 0) + ((item.variant.price or 0) if item.variant else 0)
            db.session.add(OrderItem(
                order_id=new_order.id,
                variant_id=item.variant_id,
                quantity=item.quantity,
                price=unit_price
            ))
            db.session.delete(item)

        db.session.commit()

        # ✅ 결제 페이지로 이동
        return redirect(url_for("payment", order_id=new_order.id))

    # GET: 장바구니 화면
    cart_items = base_q.all()
    total = sum(((ci.product.base_price or 0) + ((ci.variant.price or 0) if ci.variant else 0)) * ci.quantity
                for ci in cart_items)

    user_info = {}
    user_info = {}
    if current_user.is_authenticated:
        user_info = {
            "name": current_user.name,
            "phone": current_user.phone,
            "base_address": current_user.base_address,
            "detail_address": current_user.detail_address,
            "email": current_user.email
        }

    return render_template("checkout.html", cart_items=cart_items, total=total,
                           user_info=user_info, user_id=(current_user.id if current_user.is_authenticated else None))

@app.route("/payment/<int:order_id>")
def payment(order_id):
    order = Order.query.get_or_404(order_id)
    amount = sum(int(oi.price) * int(oi.quantity) for oi in order.items)  # <- amount로 계산
    user_info = User.query.get(order.user_id) if order.user_id else None

    return render_template(
        "payment.html",
        order=order,
        amount=amount,                 # <- amount 넘김
        user_info=user_info,
        imp_code=app.config["IMP_CODE"]  # <- 결제 스크립트에서 사용
    )


@app.route("/pay/prepare", methods=["POST"])
def pay_prepare():
    # 결제창 열기 전에 서버에서 merchant_uid 발급 & 금액 사전등록(선택)
    data = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    order = Order.query.get_or_404(order_id)

    expected_amount = sum(int(i.price) * int(i.quantity) for i in order.items)
    merchant_uid = f"UGA_{order.id}_{int(datetime.utcnow().timestamp())}"

    pay = Payment(order_id=order.id, merchant_uid=merchant_uid, amount=expected_amount, status="ready")
    db.session.add(pay)
    db.session.commit()

    # 아임포트 사전등록(선택)
    try:
        token = _get_iamport_token()
        requests.post(
            "https://api.iamport.kr/payments/prepare",
            headers={"Authorization": token},
            data={"merchant_uid": merchant_uid, "amount": expected_amount},
            timeout=7
        )
    except Exception:
        pass

    return jsonify(ok=True, merchant_uid=merchant_uid, amount=expected_amount, imp_code=app.config["IMP_CODE"])


@app.route("/pay/verify", methods=["POST"])
def pay_verify():
    # imp_uid로 아임포트 조회 → 금액/UID 검증 → DB 반영
    data = request.get_json(silent=True) or {}
    imp_uid = data.get("imp_uid")
    merchant_uid = data.get("merchant_uid")
    order_id = data.get("order_id")

    pay = Payment.query.filter_by(merchant_uid=merchant_uid, order_id=order_id).first()
    if not pay:
        return jsonify(ok=False, msg="payment not found"), 404

    token = _get_iamport_token()
    res = requests.get(
        f"https://api.iamport.kr/payments/{imp_uid}",
        headers={"Authorization": token},
        timeout=7
    )
    res.raise_for_status()
    info = res.json()["response"]

    paid_amount = int(info["amount"])
    status      = info["status"]              # paid, ready(vbank), cancelled 등
    method      = info.get("pay_method")
    pg          = info.get("pg_provider")

    # 금액/merchant_uid 검증
    if info["merchant_uid"] != merchant_uid:
        return jsonify(ok=False, msg="merchant_uid mismatch"), 400
    if paid_amount != pay.amount:
        return jsonify(ok=False, msg="amount mismatch"), 400

    # 상태 반영
    pay.imp_uid = imp_uid
    pay.method = method
    pay.pg_provider = pg

    order = Order.query.get_or_404(order_id)

    if status == "paid":
        pay.status = "paid"
        pay.paid_at = datetime.utcnow()
        order.status = "paid"
    elif status in ("ready", "vbank_issued"):
        pay.status = "ready"
        order.status = "pending"
    else:
        pay.status = status
        order.status = "failed"

    db.session.commit()
    return jsonify(ok=True, status=pay.status)

# -----------------------------
# 주문 완료 페이지(무통장/카드 공용)
# -----------------------------
@app.route("/order-complete/<int:order_id>")
def order_complete(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template("order_complete.html", order=order, amount=_order_sum(order))

@app.route("/remove_from_cart/<int:item_id>", methods=["POST"])
def remove_from_cart(item_id):
    cart_item = CartItem.query.get_or_404(item_id)
    db.session.delete(cart_item)
    db.session.commit()
    flash("장바구니에서 삭제되었습니다.", "success")
    return redirect(url_for("checkout"))

@app.route("/order", methods=["GET", "POST"])
def order_page():
    cart_items = CartItem.query.all()
    total = sum((item.variant.price + item.variant.product.base_price) * item.quantity for item in cart_items)

    if request.method == "POST":
        name = request.form.get("name")
        base_address = request.form.get("base_address")
        detail_address = request.form.get("detail_address")
        phone = request.form.get("phone")
        payment_method = request.form.get("payment_method")

        order = Order(
            user_id=(current_user.id if current_user.is_authenticated else None),
            name=name,
            base_address=base_address,
            detail_address=detail_address,
            phone=phone,
            payment_method=payment_method,
            status="pending"
        )
        db.session.add(order)
        db.session.flush()

        for item in cart_items:
            order_item = OrderItem(
                order_id=order.id,
                variant_id=item.variant_id,
                quantity=item.quantity,
                price=item.variant.price + item.variant.product.base_price
            )
            db.session.add(order_item)

        CartItem.query.delete()
        db.session.commit()
        flash("주문이 접수되었습니다.", "success")
        return redirect(url_for("home"))

    return render_template("order_page.html", cart_items=cart_items, total=total)

def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            flash("관리자만 접근 가능합니다.", "error")
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapped

@app.route("/admin")
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("관리자만 접근 가능합니다.", "error")
        return redirect(url_for("home"))
    # 주문 중 결제 대기중 개수
    pending_orders = Order.query.filter_by(status="pending").count()
    # 답변 대기중 문의 개수
    new_inquiries_count = Inquiry.query.filter_by(status="답변 대기").count()
    return render_template("admin/dashboard.html",
        pending_orders=pending_orders,
        new_inquiries_count=new_inquiries_count)

@app.route("/admin/products")
@login_required
def admin_products():
    if not current_user.is_admin:
        flash("관리자만 접근 가능합니다.", "error")
        return redirect(url_for("home"))
    products = Product.query.all()
    return render_template("admin/products.html", products=products)

@app.route("/admin/products/add", methods=["GET", "POST"])
@login_required
def admin_add_product():
    if not current_user.is_admin:
        flash("관리자만 접근할 수 있습니다.", "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form.get("name")
        base_price = request.form.get("base_price", type=float)
        category = request.form.get("category")
        description = request.form.get("description")

        new_product = Product(
            name=name,
            base_price=base_price,
            category=category,
            description=description
        )

        # ✅ 이미지 업로드
        image_file = request.files.get("image")
        if image_file and image_file.filename:
            filename = secure_filename(image_file.filename)
            image_path = os.path.join(current_app.root_path, "static", "images", filename)
            image_file.save(image_path)
            new_product.image = filename

        # ✅ 팜플렛 업로드
        pamphlet_file = request.files.get("pamphlet")
        if pamphlet_file and pamphlet_file.filename:
            filename = secure_filename(pamphlet_file.filename)
            pamphlet_path = os.path.join(current_app.root_path, "static", "pamphlets", filename)
            pamphlet_file.save(pamphlet_path)
            new_product.pamphlet = filename

        db.session.add(new_product)
        db.session.commit()

        flash("상품이 추가되었습니다.", "success")
        return redirect(url_for("admin_products_options"))

    return render_template("admin_add_product.html")

@app.route("/admin/products/<int:product_id>/options", methods=["GET", "POST"])
@login_required
def admin_product_options(product_id):
    if not current_user.is_admin:
        return redirect(url_for("home"))

    product = Product.query.get_or_404(product_id)

    if request.method == "POST":
        name = request.form["name"]
        values = request.form["values"].split(",")
        for v in values:
            option = ProductOption(product_id=product.id, name=name, value=v.strip())
            db.session.add(option)
        db.session.commit()
        flash("옵션이 추가되었습니다.", "success")
        # ✅ 옵션 추가 후에도 다시 옵션 페이지로 돌아옴
        return redirect(url_for("admin_product_options", product_id=product.id))

    options = ProductOption.query.filter_by(product_id=product.id).all()
    return render_template("admin/product_options.html", product=product, options=options)

@app.route("/admin/products/<int:product_id>/variants", methods=["GET", "POST"])
@login_required
def admin_product_variants(product_id):
    if not current_user.is_admin:
        return redirect(url_for("home"))

    product = Product.query.get_or_404(product_id)

    if request.method == "POST":
        selected_options = {}
        for key, value in request.form.items():
            if key.startswith("option_"):
                selected_options[key.replace("option_", "")] = value

        price = float(request.form.get("price", 0))
        stock = int(request.form.get("stock", 0))

        variant = ProductVariant(
            product_id=product.id,
            sku=f"{product.id}-{'-'.join(selected_options.values())}",
            price=price,
            stock=stock,
            options=selected_options
        )
        db.session.add(variant)
        db.session.commit()
        flash("옵션 조합이 추가되었습니다.", "success")
        return redirect(url_for("admin_product_variants", product_id=product.id))

    options = ProductOption.query.filter_by(product_id=product.id).all()
    variants = ProductVariant.query.filter_by(product_id=product.id).all()
    return render_template("admin/product_variants.html", product=product, options=options, variants=variants)

# 옵션 삭제
@app.route("/admin/products/<int:product_id>/options/<int:option_id>/delete", methods=["POST"])
@login_required
def admin_delete_option(product_id, option_id):
    if not current_user.is_admin:
        return redirect(url_for("home"))
    option = ProductOption.query.get_or_404(option_id)
    db.session.delete(option)
    db.session.commit()
    flash("옵션이 삭제되었습니다.", "success")
    return redirect(url_for("admin_product_options", product_id=product_id))

# 조합 삭제
@app.route("/admin/products/<int:product_id>/variants/<int:variant_id>/delete", methods=["POST"])
@login_required
def admin_delete_variant(product_id, variant_id):
    if not current_user.is_admin:
        return redirect(url_for("home"))
    variant = ProductVariant.query.get_or_404(variant_id)
    db.session.delete(variant)
    db.session.commit()
    flash("옵션 조합이 삭제되었습니다.", "success")
    return redirect(url_for("admin_product_variants", product_id=product_id))

# 상품 수정
@app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit_product(product_id):
    if not current_user.is_admin:
        flash("관리자만 접근할 수 있습니다.", "error")
        return redirect(url_for("home"))

    product = Product.query.get_or_404(product_id)

    if request.method == "POST":
        # 상품 기본 정보 업데이트
        product.name = request.form.get("name")
        product.base_price = request.form.get("base_price", type=float)
        product.category = request.form.get("category")
        product.description = request.form.get("description")

        # ✅ 이미지 업로드
        image_file = request.files.get("image")
        if image_file and image_file.filename:
            filename = secure_filename(image_file.filename)
            image_path = os.path.join(current_app.root_path, "static", "images", filename)
            image_file.save(image_path)
            product.image = filename

        # ✅ 팜플렛 업로드
        pamphlet_file = request.files.get("pamphlet")
        if pamphlet_file and pamphlet_file.filename:
            filename = secure_filename(pamphlet_file.filename)
            pamphlet_path = os.path.join(current_app.root_path, "static", "pamphlets", filename)
            pamphlet_file.save(pamphlet_path)
            product.pamphlet = filename

        db.session.commit()
        flash("상품이 수정되었습니다.", "success")
        return redirect(url_for("admin_products"))

    return render_template("admin/edit_product.html", product=product)

# 상품 삭제
@app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@login_required
def admin_delete_product(product_id):
    if not current_user.is_admin:
        flash("관리자만 접근할 수 있습니다.", "error")
        return redirect(url_for("index"))

    product = Product.query.get_or_404(product_id)

    # ✅ 연결된 cart_items 먼저 삭제
    CartItem.query.filter_by(product_id=product.id).delete()

    db.session.delete(product)
    db.session.commit()

    flash("상품이 삭제되었습니다.", "success")
    return redirect(url_for("admin_products"))

@app.route("/admin/videos")
@login_required
def admin_videos():
    if not current_user.is_admin:
        return redirect(url_for("home"))
    videos = Video.query.all()
    return render_template("admin/videos.html", videos=videos)

@app.route("/admin/videos/add", methods=["GET", "POST"])
@login_required
def admin_add_video():
    if not current_user.is_admin:
        return redirect(url_for("home"))
    if request.method == "POST":
        title = request.form["title"]
        file = request.files["video"]
        filename = file.filename
        file.save(os.path.join("static/videos", filename))
        video = Video(title=title, file_path=filename)
        db.session.add(video)
        db.session.commit()
        flash("영상이 추가되었습니다.", "success")
        return redirect(url_for("admin_videos"))
    return render_template("admin/video_form.html")

@app.route("/admin/videos/<int:video_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit_video(video_id):
    video = Video.query.get_or_404(video_id)

    if request.method == "POST":
        video.title = request.form["title"]

        file = request.files.get("video")
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join("static/videos", filename)
            file.save(filepath)
            video.file_path = filename

        db.session.commit()
        flash("영상이 수정되었습니다.", "success")
        return redirect(url_for("admin_videos"))

    return render_template("admin/edit_video.html", video=video)

@app.route("/admin/videos/<int:video_id>/delete", methods=["POST"])
@login_required
def admin_delete_video(video_id):
    video = Video.query.get_or_404(video_id)

    # 실제 파일도 같이 삭제 (선택)
    file_path = os.path.join("static/videos", video.file_path)
    if os.path.exists(file_path):
        os.remove(file_path)

    db.session.delete(video)
    db.session.commit()
    flash("영상이 삭제되었습니다.", "success")
    return redirect(url_for("admin_videos"))

@app.route("/admin/users", methods=["GET", "POST"])
@login_required
def admin_users():
    if not current_user.is_admin:
        flash("관리자만 접근할 수 있습니다.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        user_id = request.form.get("user_id")
        action = request.form.get("action")
        user = User.query.get(user_id)

        if user:
            if action == "dormant":
                user.status = "dormant"
                flash(f"{user.name or user.email} 님이 휴면 처리되었습니다.", "info")
            elif action == "delete":
                user.status = "deleted"
                flash(f"{user.name or user.email} 님이 탈퇴 처리되었습니다.", "warning")
            db.session.commit()
        return redirect(url_for("admin_users"))

    # GET 요청 처리
    users = User.query.all()
    now = datetime.now(KST)
    two_years_ago = now - timedelta(days=730)

    for u in users:
        if u.last_login:
            if u.last_login.tzinfo is None:
                u.last_login = u.last_login.replace(tzinfo=KST)
            u.is_dormant = u.last_login < two_years_ago
        else:
            u.is_dormant = False

    return render_template("admin/users.html", users=users, two_years_ago=two_years_ago)

@app.route("/admin/users/<int:user_id>/make_admin")
@login_required
def make_admin(user_id):
    user = User.query.get(user_id)
    if user:
        user.is_admin = True
        db.session.commit()
        flash(f"{user.email} 님이 관리자로 승격되었습니다.", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/orders", methods=["GET", "POST"])
@login_required
def admin_orders():
    if not current_user.is_admin:
        flash("관리자만 접근 가능합니다.", "error")
        return redirect(url_for("home"))

    # 상태 변경
    if request.method == "POST":
        order_id = request.form.get("order_id", type=int)
        new_status = request.form.get("status")
        if new_status == "cancelled":  # 철자 혼용 보정
            new_status = "canceled"

        order = Order.query.get(order_id)
        if order and new_status:
            order.status = new_status
            db.session.commit()
            flash(f"주문 {order.id} 상태가 '{new_status}'로 변경되었습니다.", "success")
        return redirect(url_for("admin_orders"))

    # 주문 + 아이템 + 상품 + 결제 + 유저까지 미리 로딩(N+1 방지)
    orders = (
        Order.query
        .options(
            joinedload(Order.items)
              .joinedload(OrderItem.variant)
              .joinedload(ProductVariant.product),
            joinedload(Order.payment),
            joinedload(Order.user),
        )
        .order_by(Order.created_at.desc())
        .all()
    )

    # 템플릿에서 바로 쓰기 편하게 요약 필드 계산
    for o in orders:
        names = []
        for it in o.items:
            product = it.variant.product if (it.variant and it.variant.product) else None
            names.append(product.name if product else "(삭제된 상품)")
        summary = names[0] + (f" 외 {len(names)-1}개" if len(names) > 1 else "") if names else "-"

        qty_sum       = sum((it.quantity or 0) for it in o.items)
        total_amount  = sum(int(it.price or 0) * int(it.quantity or 0) for it in o.items)

        who    = (o.user.name if o.user else (o.name or "비회원"))
        email  = (o.user.email if o.user else (o.guest_email or "-"))
        phone  = o.phone or (o.user.phone if (o.user and getattr(o.user, "phone", None)) else "-")
        address = " ".join([x for x in [o.base_address, o.detail_address] if x]) or "-"

        pay_status = o.payment.status if o.payment else "-"

        # 동적 속성(템플릿에서 o._xxx로 접근)
        o._summary      = summary
        o._qty_sum      = int(qty_sum)
        o._total_amount = int(total_amount)
        o._who          = who
        o._email        = email
        o._phone        = phone
        o._address      = address
        o._pay_status   = pay_status

        # 철자 혼용 보정(표시용)
        if getattr(o, "status", None) == "cancelled":
            o.status = "canceled"

    return render_template("admin/admin_orders.html",
                           orders=orders,
                           status_options=STATUS_OPTIONS)

@app.post("/admin/orders/<int:order_id>/cancel")
@login_required
def admin_cancel_order(order_id):
    if not current_user.is_admin:
        flash("관리자만 접근 가능합니다.", "error")
        return redirect(url_for("home"))

    order = Order.query.options(joinedload(Order.payment)).get_or_404(order_id)
    pay = order.payment

    reason = (request.form.get("reason") or "관리자 취소").strip()
    partial_amount = request.form.get("amount", type=int)

    # 가상계좌 환불정보 (입금 후 취소 시 필요)
    refund_bank    = request.form.get("refund_bank")
    refund_account = request.form.get("refund_account")
    refund_holder  = request.form.get("refund_holder")

    if not pay:
        # 결제가 아예 생성되지 않은 주문이면 DB 상태만 취소
        order.status = "canceled"
        db.session.commit()
        flash("결제내역이 없어 주문만 취소 처리했습니다.", "info")
        return redirect(url_for("admin_orders"))

    try:
        if pay.status == "paid":
            # 카드/계좌이체/간편결제/가상계좌(입금 후) → 실환불
            cancel_portone_payment(
                imp_uid=pay.imp_uid,
                amount=partial_amount,  # 없으면 전액 취소
                reason=reason,
                # vbank(입금 후)일 때만 계좌정보 필요
                refund_bank=refund_bank if pay.method == "vbank" else None,
                refund_account=refund_account if pay.method == "vbank" else None,
                refund_holder=refund_holder if pay.method == "vbank" else None,
            )
            pay.status = "cancelled"   # PG 표기
            order.status = "canceled"  # 우리 시스템 표기
            db.session.commit()
            flash("PG 환불(결제취소)이 완료되었습니다.", "success")

        elif pay.status in ("ready", "vbank_issued"):
            # 가상계좌 '발급만' 되었고 미입금 → 실 결제 없음, 주문만 취소
            order.status = "canceled"
            pay.status = "cancelled"
            db.session.commit()
            flash("가상계좌 미입금 건: 주문만 취소 처리했습니다.", "info")

        else:
            # 이미 취소 등
            order.status = "canceled"
            db.session.commit()
            flash("이미 취소된 결제이거나 취소할 수 없는 상태입니다.", "info")

    except Exception as e:
        flash(f"환불 실패: {e}", "error")

    return redirect(url_for("admin_orders"))


@app.route("/admin/inquiries", methods=["GET", "POST"])
@login_required
def admin_inquiries():
    # 👉 관리자 권한 체크 (원하시면 조건 강화 가능)
    if not current_user.is_admin:
        flash("관리자만 접근 가능합니다.", "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        inquiry_id = request.form.get("inquiry_id")
        answer = request.form.get("answer")

        inquiry = Inquiry.query.get(inquiry_id)
        if inquiry:
            inquiry.answer = answer
            inquiry.status = "답변 완료"
            inquiry.answered_at = datetime.now(KST)
            db.session.commit()
            flash("답변이 등록되었습니다.", "success")

        return redirect(url_for("admin_inquiries"))

    inquiries = Inquiry.query.order_by(Inquiry.created_at.desc()).all()
    return render_template("admin_inquiries.html", inquiries=inquiries)


@app.route('/company')
def company():
    return render_template('company.html')

@app.route('/contact', methods=['GET','POST'])
def contact():
    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")

        if current_user.is_authenticated:
            user_id = current_user.id
            guest_email = None
        else:
            user_id = None
            guest_email = request.form.get("email")
            if not guest_email:
                flash("비회원은 이메일을 입력해야 합니다.", "error")
                return redirect(url_for("contact"))

        inquiry = Inquiry(
            user_id=user_id,
            guest_email=guest_email,
            title=title,
            content=content,
            created_at=datetime.now(KST),
            status="답변 대기"
        )
        db.session.add(inquiry)
        db.session.commit()

        flash("문의가 접수되었습니다.", "success")
        return redirect(url_for("home"))

    return render_template("contact.html")

@app.route('/search')
def search():
    q = request.args.get("name","")
    category = request.args.get("category","")
    price_min = request.args.get("price_min",0,type=int)
    price_max = request.args.get("price_max",9999999,type=int)
    video = request.args.get("video","false")=="true"
    query = Product.query
    if q:
        query = query.filter(Product.name.contains(q))
    if category:
        query = query.filter(Product.category==category)
    query = query.filter(Product.base_price>=price_min, Product.base_price<=price_max)
    products = query.all()
    
    videos = []
    if video:
        if q:
            videos = Video.query.filter(Video.title.contains(q)).all()
        else:
            videos = Video.query.all()
    categories = [c[0] for c in db.session.query(Product.category).distinct()]
    return render_template("search.html", products=products, videos=videos, categories=categories, video_filter=True,q=q)

@app.route("/debug")
def debug():
    return f"로그인 여부: {current_user.is_authenticated}, id={getattr(current_user,'id',None)}"

@app.route('/autocomplete')
def autocomplete():
    q = request.args.get("q","")
    results = []
    if q:
        results = [p.name for p in Product.query.filter(Product.name.contains(q)).all()]
    return jsonify(results)
@app.route("/db_tables")
def db_tables():
    try:
        tables = db.inspect(db.engine).get_table_names()
        return jsonify({"tables": tables})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/make_admin_page", methods=["GET", "POST"])
def make_admin_page():
    message = None
    if request.method == "POST":
        email = request.form.get("email")
        user = User.query.filter_by(email=email).first()
        if user:
            user.is_admin = True
            db.session.commit()
            message = f"{email} → 관리자 권한 부여 완료 ✅"
        else:
            message = f"{email} 계정을 찾을 수 없습니다 ❌"
    return render_template("make_admin.html", message=message)

with app.app_context():
    db.create_all()
    print("✅ DB schema created (or already exists)")

if __name__=="__main__":
    app.run(debug=True)
