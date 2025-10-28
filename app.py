from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, current_app, abort
from flask_babel import Babel, _
from flask_login import UserMixin
from flask_login import current_user, login_required
import re
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, cast, String
from sqlalchemy.dialects.mysql import LONGBLOB
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
import requests
import os
import random, time, string
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask_migrate import Migrate
from sqlalchemy.dialects.mysql import JSON
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
import uuid
import json
from threading import Thread
import socket

app = Flask(__name__)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

login_manager = LoginManager(app)
login_manager.login_view = "login"  # 로그인 안 된 상태에서 접근 시 이동할 뷰

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 현재 실행 중인 호스트 이름 확인
HOSTNAME = socket.gethostname()

from dotenv import load_dotenv
if "ugamall-server" in HOSTNAME or "ubuntu" in HOSTNAME:
    # ✅ 서버용 환경파일
    dotenv_path = "/var/www/ugamall-flask-server/.env"
else:
    # ✅ 로컬 개발용 환경파일
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env.local")
load_dotenv(dotenv_path=dotenv_path)  # ✅ .env 파일 자동 로드

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
#app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL").replace("postgres://", "postgresql://")

app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# 안정성 옵션(아이들 타임아웃 대비)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 280
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")

app.config['BABEL_DEFAULT_LOCALE'] = 'ko'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'

app.config["IMP_CODE"]   = os.getenv("IMP_CODE")
app.config["IMP_KEY"]    = os.getenv("IMP_KEY")
app.config["IMP_SECRET"] = os.getenv("IMP_SECRET")
app.config["IMP_CHANNEL_INICIS"] = os.getenv("IMP_CHANNEL_INICIS")
app.config["IMP_CHANNEL_KAKAOPAY"] = os.getenv("IMP_CHANNEL_KAKAOPAY")

db = SQLAlchemy(app)
migrate = Migrate(app, db)
# ----------------------------
# 비밀번호 찾기 - 이메일 전송
# ----------------------------
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_DEFAULT_SENDER=f"UGAMALL <{os.getenv('MAIL_USERNAME')}>"
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

    coupons = db.relationship("UserCoupon", back_populates="user", cascade="all, delete-orphan")

class Product(db.Model):
    __tablename__ = "product"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    base_price = db.Column(db.Integer, nullable=False, default=0)
    description = db.Column(db.Text)
    image_data = db.Column(LONGBLOB)
    image_mime = db.Column(db.String(50))
    category = db.Column(db.String(50))
    pamphlet_data = db.Column(LONGBLOB)
    pamphlet_mime = db.Column(db.String(50))
    pamphlet_name = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)  # ✅ 운영용: 상품 활성/비활성 상태
    discount_percent = db.Column(db.Integer, default=0)   # ✅ 시즌 할인율 (예: 20%)
    
    def final_price(self):
        if self.discount_percent and self.discount_percent > 0:
            return int(self.base_price * (100 - self.discount_percent) / 100)
        return self.base_price

    product_options = db.relationship("ProductOption", back_populates="product", cascade="all, delete-orphan")
    variants = db.relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")
    cart_items = db.relationship("CartItem", back_populates="product", cascade="all, delete-orphan")

class Coupon(db.Model):
    __tablename__ = "coupons"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)              # 쿠폰명
    description = db.Column(db.String(255))                       # 설명
    discount_type = db.Column(db.String(10), default="percent")   # "percent" or "fixed"
    discount_value = db.Column(db.Integer, nullable=False)        # 할인 값 (ex. 10% or 5000원)
    min_amount = db.Column(db.Integer, default=0)                 # 최소 주문 금액
    valid_from = db.Column(db.DateTime, nullable=False)
    valid_to = db.Column(db.DateTime, nullable=False)
    active = db.Column(db.Boolean, default=True)

    user_coupons = db.relationship("UserCoupon", back_populates="coupon", cascade="all, delete-orphan")

class UserCoupon(db.Model):
    __tablename__ = "user_coupons"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    coupon_id = db.Column(db.Integer, db.ForeignKey("coupons.id", ondelete="CASCADE"))
    used = db.Column(db.Boolean, default=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="coupons")
    coupon = db.relationship("Coupon", back_populates="user_coupons")

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
    price = db.Column(db.Integer, nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    options = db.Column(JSON, nullable=False)  # {"사이즈": "250", "색상": "파랑"}

    product = db.relationship("Product", back_populates="variants")
    order_items = db.relationship("OrderItem", back_populates="variant")
    # ✅ cart_items 관계는 단방향으로만 사용 (필요하다면 backref 사용)
    cart_items = db.relationship("CartItem", back_populates="variant", cascade="all, delete-orphan")

class Review(db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)   # 1~5
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship("Product", backref="reviews")
    user = db.relationship("User", backref="reviews")

class Advertisement(db.Model):
    __tablename__ = "advertisements"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    subtitle = db.Column(db.String(255))
    description = db.Column(db.Text)
    link_url = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    images = db.relationship("AdvertisementImage", backref="ad", cascade="all, delete")

class AdvertisementImage(db.Model):
    __tablename__ = "advertisement_images"
    id = db.Column(db.Integer, primary_key=True)
    ad_id = db.Column(db.Integer, db.ForeignKey("advertisements.id"), nullable=False)
    image_data = db.Column(db.LargeBinary(length=(2**24)))  # ✅ MEDIUMBLOB (16MB)
    image_mime = db.Column(db.String(100))

class Video(db.Model):
    __tablename__ = 'video'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    tags = db.Column(db.String(200))  # ✅ 태그(쉼표 구분) 추가

    # ✅ DB에 대용량 바이너리 저장 가능하도록 확장
    video_data = db.Column(LONGBLOB)         # <-- 여기!
    video_mime = db.Column(db.String(50))

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
    is_read = db.Column(db.Boolean, default=False)

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
    is_read = db.Column(db.Boolean, default=False)
    applied_user_coupon_id = db.Column(db.Integer, db.ForeignKey("user_coupons.id"), nullable=True)
    discount_amount        = db.Column(db.Integer, default=0)
    @property
    def total_price(self):
        total = 0
        for item in self.items:
            total += item.discount_price or item.original_price or 0
        return total

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
    original_price = db.Column(db.Integer)   # 정가
    discount_price = db.Column(db.Integer)   # 실제 결제 단가
    discount_reason = db.Column(db.String(100))  # 쿠폰명 등

    order = db.relationship("Order", back_populates="items")
    variant = db.relationship("ProductVariant", back_populates="order_items")

class OrderReturn(db.Model):
    __tablename__ = "order_returns"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'return' or 'exchange'
    status = db.Column(db.String(20), default="요청접수")  # 요청접수 / 처리중 / 완료
    created_at = db.Column(db.DateTime, default=datetime.now(KST))

    user = db.relationship("User", backref="returns")
    order = db.relationship("Order", backref="return_request")
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

@app.template_filter('kst')
def format_kst(dt):
    """서버 UTC datetime을 KST로 변환해서 YYYY-MM-DD HH:MM 형태로 반환"""
    if not dt:
        return ''
    try:
        return dt.astimezone(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return dt.strftime('%Y-%m-%d %H:%M')
    
@app.template_filter("status_label")
def status_label_filter(status):
    mapping = {
        "주문 접수": "주문 접수",
        "입금대기": "입금대기",
        "결제대기": "결제대기",
        "결제완료": "결제완료",
        "배송중": "배송중",
        "배송완료": "배송완료",
        "canceled": "취소됨",
        "paid": "결제완료",
        "delivered": "배송완료",
        "pending": "주문 접수"
    }
    return mapping.get(status, status)

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

@app.context_processor
def inject_admin_alerts():
    if current_user.is_authenticated and current_user.is_admin:
        pending_orders = Order.query.filter(
            Order.status.in_(["pending", "ready", "입금대기", "결제대기"])
        ).count()
        new_inquiries_count = Inquiry.query.filter_by(is_read=False).count()
        return dict(
            pending_orders=pending_orders,
            new_inquiries_count=new_inquiries_count
        )
    return {}

@app.context_processor
def inject_admin_alerts():
    if current_user.is_authenticated and current_user.is_admin:
        unread_orders = Order.query.filter_by(is_read=False).count()
        unread_inquiries = Inquiry.query.filter_by(is_read=False).count()
        return dict(
            unread_orders=unread_orders,
            unread_inquiries=unread_inquiries,
            admin_total_alerts=unread_orders + unread_inquiries
        )
    return {}

# ----------------------------
# 비동기 메일 발송 함수
def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

def send_email(subject, recipients, body):
    msg = Message(subject=subject, recipients=recipients, body=body)
    Thread(target=send_async_email, args=(app, msg)).start()
# -----------------------------
import time, hmac, hashlib, base64, requests, json, os

def send_sms(phone, code):
    """네이버 클라우드 SENS로 인증번호 전송"""
    access_key = os.getenv("NCP_ACCESS_KEY")
    secret_key = os.getenv("NCP_SECRET_KEY")
    service_id = os.getenv("NCP_SERVICE_ID")
    sender = os.getenv("NCP_SENDER_NUMBER")

    url = f"https://sens.apigw.ntruss.com/sms/v2/services/{service_id}/messages"
    timestamp = str(int(time.time() * 1000))
    method = "POST"
    uri = f"/sms/v2/services/{service_id}/messages"
    message = f"{method} {uri}\n{timestamp}\n{access_key}"

    signature = base64.b64encode(
        hmac.new(
            bytes(secret_key, "utf-8"),
            bytes(message, "utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    body = {
        "type": "SMS",
        "from": sender,
        "content": f"[유가몰] 인증번호 [{code}] 를 입력해주세요.",
        "messages": [{"to": phone}],
    }

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "x-ncp-apigw-timestamp": timestamp,
        "x-ncp-iam-access-key": access_key,
        "x-ncp-apigw-signature-v2": signature,
    }

    response = requests.post(url, headers=headers, data=json.dumps(body))
    return response.json()
#-----------------------------
def _get_iamport_token():
    url = "https://api.iamport.kr/users/getToken"
    # 혹시 모를 앞뒤 공백/줄바꿈 제거
    imp_key = (current_app.config["IMP_KEY"] or "").strip()
    imp_secret = (current_app.config["IMP_SECRET"] or "").strip()

    payload = {"imp_key": imp_key, "imp_secret": imp_secret}
    try:
        res = requests.post(
            url,
            data=payload,  # x-www-form-urlencoded
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=7,
        )
        # 200이 아니면, 포트원에서 주는 본문 그대로 찍어서 원인 확인
        if res.status_code != 200:
            print("❌ [토큰 HTTP 오류]", res.status_code, res.text)
            return None

        data = res.json()
        if data.get("code") != 0:
            # 예: {"code":-1,"message":"imp_key/imp_secret not matched", ...}
            print("❌ [토큰 응답 오류]", data)
            return None

        token = data["response"]["access_token"]
        print("✅ TOKEN OK:", token[:12], "…")
        return token
    except Exception as e:
        print("❌ [토큰 예외]", repr(e))
        return None

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
    # per-item 할인은 안 나눔. 주문 전체 할인만 적용.
    items_total = sum(int(i.original_price or 0) * int(i.quantity or 0) for i in order.items)
    return max(0, items_total - int(order.discount_amount or 0))
#-----------------------------
# -----------------------------
# 날짜 계산 헬퍼
# -----------------------------
def _compute_date_range(period: str | None, start_date_str: str | None, end_date_str: str | None):
    now = datetime.now(KST)
    if start_date_str and end_date_str:
        try:
            start_dt = datetime.strptime(start_date_str, "%Y-%m").replace(tzinfo=KST)
            end_base = datetime.strptime(end_date_str, "%Y-%m").replace(tzinfo=KST)
            if end_base.month == 12:
                end_dt = end_base.replace(year=end_base.year + 1, month=1)
            else:
                end_dt = end_base.replace(month=end_base.month + 1)
            return start_dt, end_dt
        except Exception:
            pass

    days = {"1m": 30, "3m": 90, "6m": 180, "5y": 5 * 365}.get(period or "1m", 30)
    start_dt = now - timedelta(days=days)
    end_dt = now + timedelta(days=1)  # ✅ 오늘 포함 (UTC 문제 방지)

    return start_dt, end_dt
# -----------------------------
# 주문 상태 한국어 변환
# -----------------------------
STATUS_LABEL_TEXT = {
    # 영어 상태코드
    "paid": "결제완료",
    "ready": "입금대기",
    "pending": "결제대기",
    "failed": "결제실패",
    "canceled": "취소됨",
    "shipped": "배송중",
    "delivered": "배송완료",
    "returned": "반품완료",
    "exchanged": "교환완료",

    # 한글 상태코드도 추가
    "주문 접수": "주문 접수",
    "입금대기": "입금대기",
    "결제대기": "결제대기",
    "결제완료": "결제완료",
    "배송중":   "배송중",
    "배송완료": "배송완료",
    "취소됨":   "취소됨",
    "반품요청": "반품요청",
    "교환요청": "교환요청",
    "반품처리중": "반품처리중",
    "교환처리중": "교환처리중",

    "-": "-",
    None: "-"
}

# 드롭다운 옵션(변경용)
STATUS_OPTIONS = [
    {"value": "주문 접수", "label": "주문 접수"},
    {"value": "입금대기", "label": "입금대기"},
    {"value": "결제대기", "label": "결제대기"},
    {"value": "결제완료", "label": "결제완료"},
    {"value": "배송중", "label": "배송중"},
    {"value": "배송완료", "label": "배송완료"},
    {"value": "취소됨", "label": "취소됨"},
]

@app.template_filter("status_label")
def status_label(value):
    return STATUS_LABEL_TEXT.get(value, value)

# -----------------------------
# 라우트
# -----------------------------
@app.route('/')
def home():
    ads = Advertisement.query.filter_by(is_active=True).order_by(Advertisement.order).all()
    latest_video = Video.query.order_by(Video.id.desc()).first()
    # 🔽 숨김 처리된 상품은 제외
    products = Product.query.filter_by(is_active=True).order_by(Product.id.desc()).limit(8).all()
    return render_template('index.html',ads=ads, latest_video=latest_video, products=products)

@app.route('/set_lang/<lang>')
def set_lang(lang):
    session['lang'] = lang
    return redirect(request.referrer or url_for('home'))

@app.route("/debug_lang")
def debug_lang():
    return f"Current lang = {session.get('lang')}"

@app.route("/ad_image/<int:image_id>")
def ad_image(image_id):
    img = AdvertisementImage.query.get_or_404(image_id)
    return Response(img.image_data, mimetype=img.image_mime)

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
    print("🟨 register_info 세션 상태:", dict(session))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        name = request.form.get("name", "").strip()
        base_address = request.form.get("address", "").strip()
        detail_address = request.form.get("detail_address", "").strip()
        phone = request.form.get("phone", "").strip()

        # ✅ 이메일 인증 여부 확인
        if not session.get("email_verified") or session.get("verified_email") != email:
            flash("이메일 인증을 완료해야 회원가입이 가능합니다.", "error")
            return render_template(
                "auth/register_info.html",
                email=email, name=name, phone=phone,
                base_address=base_address, detail_address=detail_address
            )

        # ✅ 이메일 중복
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("이미 사용 중인 이메일입니다.", "error")
            return redirect(url_for("register_info"))

        # ✅ 비밀번호 일치
        if password != password_confirm:
            flash("비밀번호가 일치하지 않습니다.", "error")
            return redirect(url_for("register_info"))

        # ✅ 비밀번호 규칙
        pw_policy = re.compile(r"^(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")
        if not pw_policy.match(password):
            flash("비밀번호는 8자 이상이며 숫자와 특수문자를 포함해야 합니다.", "error")
            return redirect(url_for("register_info"))

        # ✅ 회원 생성
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

        # 세션 초기화
        session.pop("email_verified", None)
        session.pop("verified_email", None)

        flash("회원가입이 완료되었습니다. 로그인해주세요.", "success")
        return redirect(url_for("login"))

    return render_template("auth/register_info.html")

@app.route("/check_email", methods=["POST"])
def check_email():
    email = request.form.get("email")
    exists = User.query.filter_by(email=email).first() is not None
    return jsonify({"exists": exists})

@app.route("/delete_account", methods=["POST"])
@login_required
def delete_account():
    data = request.get_json()
    password = data.get("password")

    if not check_password_hash(current_user.password_hash, password):
        return jsonify({"success": False, "message": "비밀번호가 일치하지 않습니다."}), 400

    try:
        # 관련 데이터 삭제
        db.session.delete(current_user)
        db.session.commit()
        logout_user()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ 회원탈퇴 실패:", e)
        return jsonify({"success": False, "message": "서버 오류가 발생했습니다."}), 500

@app.route("/guest_orders", methods=["GET", "POST"])
def guest_orders():
    if request.method == "POST":
        email = request.form.get("email")
        order_id = request.form.get("order_id")  # 선택 입력

        query = Order.query.filter_by(guest_email=email)
        query = query.filter(Order.status != "failed")

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

    res = send_sms(phone, code)
    if res.get("statusCode") == "202":
        return jsonify({"status": "ok"})
    else:
        return jsonify({"status": "error", "msg": res})
    
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
@login_required
def mypage():
    user = current_user

    # ✅ POST 요청 (개인정보/비밀번호 수정)
    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "info":
            user.name = request.form.get("name")
            user.base_address = request.form.get("base_address", "")
            user.detail_address = request.form.get("detail_address", "")
            user.phone = request.form.get("phone", "")
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

    # ✅ GET 요청: 주문내역 필터링
    period = request.args.get("period", "1m")
    search_query = request.args.get("q", "").strip()

    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    now = datetime.utcnow() + timedelta(hours=9)

    # 직접 입력한 기간이 있으면 그걸 우선 적용
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m")
            # 월말 포함
            next_month = datetime.strptime(end_date_str, "%Y-%m")
            if next_month.month == 12:
                next_month = next_month.replace(year=next_month.year + 1, month=1)
            else:
                next_month = next_month.replace(month=next_month.month + 1)
            end_date = next_month
        except Exception:
            start_date = now - timedelta(days=30)
            end_date = now
    else:
        # 버튼으로 선택한 기간
        start_date = {
            "1m": now - timedelta(days=30),
            "3m": now - timedelta(days=90),
            "6m": now - timedelta(days=180),
            "5y": now - timedelta(days=5 * 365)
        }.get(period, now - timedelta(days=30))
        end_date = now

    # 🔍 주문 필터링 쿼리
    orders_query = Order.query.filter(
        Order.user_id == user.id, 
        Order.status != "failed",
        Order.created_at >= start_date,
        Order.created_at <= end_date
    ).order_by(Order.created_at.desc())

    if search_query:
        orders_query = (
            orders_query.join(OrderItem)
                        .join(ProductVariant)
                        .join(Product)
                        .filter(Product.name.ilike(f"%{search_query}%"))
        )

    orders = orders_query.all()
    inquiries = Inquiry.query.filter_by(user_id=user.id).order_by(Inquiry.created_at.desc()).all()
    user_coupons = UserCoupon.query.filter_by(user_id=user.id).all()

    return render_template(
        "mypage.html",
        user=user,
        orders=orders,
        inquiries=inquiries,
        user_coupons=user_coupons,
        selected_period=period,
        search_query=search_query,
        start_date=start_date_str,
        end_date=end_date_str
    )

@app.route("/mypage/orders")
@login_required
def mypage_orders_api():
    """AJAX용 주문내역 필터 API"""
    user = current_user
    period = request.args.get("period", "1m")
    search_query = request.args.get("q", "").strip()
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    now = datetime.utcnow() + timedelta(hours=9)

    # ✅ 날짜 계산
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m")
            next_month = datetime.strptime(end_date_str, "%Y-%m")
            if next_month.month == 12:
                next_month = next_month.replace(year=next_month.year + 1, month=1)
            else:
                next_month = next_month.replace(month=next_month.month + 1)
            end_date = next_month
        except Exception:
            start_date = now - timedelta(days=30)
            end_date = now
    else:
        start_date = {
            "1m": now - timedelta(days=30),
            "3m": now - timedelta(days=90),
            "6m": now - timedelta(days=180),
            "5y": now - timedelta(days=5 * 365)
        }.get(period, now - timedelta(days=30))
        end_date = now

    # ✅ 쿼리
    orders_query = Order.query.filter(
        Order.user_id == user.id,
        Order.status != "failed",
        Order.created_at >= start_date,
        Order.created_at <= end_date
    ).order_by(Order.created_at.desc())

    if search_query:
        orders_query = (
            orders_query.join(OrderItem)
                        .join(ProductVariant)
                        .join(Product)
                        .filter(Product.name.ilike(f"%{search_query}%"))
        )

    orders = orders_query.all()

    # ✅ JSON 형태로 반환
    result = []
    for o in orders:
        order_data = {
            "id": o.id,
            "created_at": (o.created_at + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
            "status": o.status,
            "status_label": STATUS_LABEL_TEXT.get(o.status, o.status),
            "items": []
        }
        for item in o.items:
            order_data["items"].append({
                "name": item.variant.product.name,
                "image": url_for("serve_product_image", product_id=item.variant.product.id),
                "quantity": item.quantity,
                "original_price": item.original_price,
                "discount_price": item.discount_price,
            })
        result.append(order_data)

    return jsonify(result)

@app.route("/api/reorder/<int:order_id>", methods=["POST"])
@login_required
def api_reorder(order_id):
    """AJAX 요청: 이전 주문 상품을 다시 장바구니에 담기"""
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first()
    if not order:
        return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

    added_count = 0
    skipped = 0

    for item in order.items:
        variant = item.variant
        if not variant or variant.stock <= 0:
            skipped += 1
            continue

        cart_item = CartItem.query.filter_by(
            user_id=current_user.id,
            product_id=variant.product_id,
            variant_id=variant.id
        ).first()

        if cart_item:
            cart_item.quantity += item.quantity
        else:
            db.session.add(
                CartItem(
                    user_id=current_user.id,
                    product_id=variant.product_id,
                    variant_id=variant.id,
                    quantity=item.quantity,
                )
            )
        added_count += 1

    db.session.commit()

    if added_count == 0:
        msg = "추가 가능한 상품이 없습니다." if skipped else "담을 상품이 없습니다."
        return jsonify({"success": False, "message": msg}), 400

    return jsonify({
        "success": True,
        "message": f"{added_count}개의 상품이 장바구니에 담겼습니다."
    })

@app.route("/cancel_order/<int:order_id>", methods=["POST"])
@login_required
def cancel_order(order_id):
    """사용자 주문취소: 배송중 이전 상태에서만 가능"""
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()

    # 배송중 이후 상태면 거부
    if order.status in ["배송중", "배송완료", "canceled", "취소됨"]:
        flash("배송중 이후에는 주문을 취소할 수 없습니다.", "error")
        return redirect(url_for("mypage"))

    # 결제대기 or 입금대기 or 결제완료 상태면 취소 가능
    order.status = "취소됨"

    # 결제 정보도 취소로 표시
    payment = Payment.query.filter_by(order_id=order.id).first()
    if payment:
        payment.status = "cancelled"

    # ✅ 쿠폰 복구 (다시 사용 가능하게)
    if order.applied_user_coupon_id:
        uc = UserCoupon.query.get(order.applied_user_coupon_id)
        if uc and uc.used:
            uc.used = False
            uc.used_at = None  # 복구 시점 초기화
            db.session.add(uc)

    db.session.commit()
    flash(f"주문번호 {order.id}이(가) 취소되었습니다.", "success")
    return redirect(url_for("mypage"))

@app.route("/return_exchange/<int:order_id>", methods=["POST"])
@login_required
def return_exchange(order_id):
    """사용자 반품/교환 신청"""
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()

    # 배송완료 상태에서만 가능
    if order.status not in ["배송완료"]:
        flash("배송이 완료된 주문만 반품 또는 교환이 가능합니다.", "error")
        return redirect(url_for("mypage"))

    request_type = request.form.get("request_type")
    reason = (request.form.get("reason") or "").strip()

    if request_type not in ["반품", "교환"]:
        flash("잘못된 요청 유형입니다.", "error")
        return redirect(url_for("mypage"))

    # 주문 상태 변경
    if request_type == "반품":
        order.status = "반품요청"
    elif request_type == "교환":
        order.status = "교환요청"

    db.session.commit()

    # ✅ 관리자 알림용 (선택: 이메일 등으로 알림 가능)
    print(f"📦 [사용자 요청] 주문 {order.id} - {request_type} 요청 사유: {reason}")

    flash(f"{request_type} 신청이 접수되었습니다. 관리자 확인 후 진행됩니다.", "success")
    return redirect(url_for("mypage"))

@app.route("/order/request_return", methods=["POST"])
@login_required
def request_return():
    order_id = request.form.get("order_id", type=int)
    req_type = request.form.get("type")  # 'return' or 'exchange'
    reason = request.form.get("reason", "").strip()

    if not order_id or not req_type or not reason:
        flash("모든 항목을 입력해주세요.", "error")
        return redirect(url_for("mypage"))

    # 이미 존재하는지 확인
    existing = OrderReturn.query.filter_by(order_id=order_id).first()
    if existing:
        flash("이미 신청이 접수되었습니다.", "error")
        return redirect(url_for("mypage"))

    # ✅ OrderReturn 테이블에 새 요청 저장
    new_return = OrderReturn(
        user_id=current_user.id,
        order_id=order_id,
        type=req_type,
        reason=reason,
        status="요청접수",
        created_at=datetime.now()
    )
    db.session.add(new_return)

    # 주문 테이블 상태도 함께 변경
    order = Order.query.get(order_id)
    if order:
        order.status = "요청접수"
    db.session.commit()

    flash(f"{'반품' if req_type == 'return' else '교환'} 신청이 접수되었습니다.", "success")
    return redirect(url_for("mypage"))

@app.route("/my_coupons")
@login_required
def my_coupons():
    user_coupons = UserCoupon.query.filter_by(user_id=current_user.id).all()
    return render_template("my_coupons.html", user_coupons=user_coupons)

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
        msg = Message(_("비밀번호 재설정 안내"), recipients=[email])
        msg.html = f"""
        <div style="font-family: 'Noto Sans KR', sans-serif; max-width: 480px; margin: auto; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; background-color: #ffffff;">
          <div style="text-align: center; padding: 32px 20px 16px;">
            <img src="https://ugamall.co.kr/static/images/Uga_logo.png" alt="UGAMALL" style="height: 38px; margin-bottom: 20px;">
          </div>

          <hr style="border:none; border-top:1px solid #e5e7eb; margin:0;">

          <div style="padding: 32px 28px 24px; text-align: center;">
            <h2 style="font-size: 20px; font-weight: 700; color: #111827; margin-bottom: 12px;">{_('비밀번호 재설정을 요청하셨습니다.')}</h2>

            <p style="font-size: 15px; color: #374151; line-height: 1.6; margin-bottom: 4px;">
              {_('안녕하세요,')} <strong>{user.name}</strong>{_('님')}.
            </p>
            <p style="font-size: 15px; color: #374151; line-height: 1.6; margin-bottom: 20px;">
              <strong>{_('유가몰')}</strong> {_('계정의 비밀번호 재설정을 요청하셨습니다.')}<br>
              {_('아래 버튼을 클릭하여 새로운 비밀번호를 설정해주세요.')}<br>
              {_('이 링크는')} <strong>{_('1시간 후 만료')}</strong>{_('됩니다.')}
            </p>

            <a href="{reset_url}" 
               style="display: inline-block; background-color: #111827; color: #ffffff; font-weight: 600; padding: 14px 40px; border-radius: 6px; text-decoration: none; font-size: 15px; margin-top: 10px;">
               {_('비밀번호 재설정')}
            </a>

            <p style="font-size: 13px; color: #9ca3af; margin-top: 32px; line-height: 1.6;">
              {_('본 메일은 발신 전용이며, 회신되지 않습니다.')}<br>
              <strong>{_('유가몰')}</strong>{_('은 고객님의 계정을 안전하게 보호하기 위해 최선을 다하고 있습니다.')}
            </p>
          </div>

          <hr style="border:none; border-top:1px solid #e5e7eb; margin:0;">

          <div style="text-align: center; background-color: #f9fafb; padding: 16px; font-size: 12px; color: #9ca3af;">
            © 2025 UGAMALL. All rights reserved.
          </div>
        </div>
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
    sort = request.args.get("sort", "new")

    query = Product.query.filter(Product.is_active == True)   # 🔽 조건 추가

    if name:
        query = query.filter(Product.name.contains(name))
    if category:
        query = query.filter(Product.category == category)

    query = query.filter(Product.base_price >= price_min, Product.base_price <= price_max)

    # ✅ 정렬 조건 추가
    if sort == "low":
        query = query.order_by(Product.base_price.asc())
    elif sort == "high":
        query = query.order_by(Product.base_price.desc())
    elif sort == "name":
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.id.desc())  # 최신순 (id 기준)

    products = query.all()
    categories = [c[0] for c in db.session.query(Product.category).distinct()]
    return render_template("products.html", products=products, categories=categories,selected_sort=sort)

@app.route('/products/<int:product_id>')
def product_detail(product_id):
    # 🔽 숨김 상품은 접근 불가
    product = Product.query.filter_by(id=product_id, is_active=True).first_or_404()

    # 같은 카테고리 상품도 is_active=True 조건 추가
    related_products = Product.query.filter(
        Product.category == product.category,
        Product.id != product.id,
        Product.is_active == True
    ).limit(4).all()

    # ✅ 옵션 키 추출 (첫 번째 variant 기준)
    option_keys = []
    if product.variants and product.variants[0].options:
        option_keys = list(product.variants[0].options.keys())
    else:
        # 🔹 variants가 아직 없으면 product_options에서 추출
        option_keys = [opt.name for opt in ProductOption.query.filter_by(product_id=product.id).distinct()]

    # ✅ variants JSON 직렬화 (Object of type ProductVariant 에러 방지)
    variant_list = []
    for v in product.variants:
        variant_list.append({
            "id": v.id,
            "options": v.options or {},   # JSON 그대로 전달
            "price": v.price or 0,
            "stock": v.stock or 0
        })

    return render_template(
        "product_detail.html",
        product=product,
        related_products=related_products,
        option_keys=option_keys,
        variants_json=variant_list  # 🔹 추가된 부분
    )

@app.route("/products/<int:product_id>/review", methods=["POST"])
@login_required
def add_review(product_id):
    rating = int(request.form.get("rating", 0))
    content = request.form.get("content", "").strip()
    if rating < 1 or rating > 5:
        flash("평점은 1~5 사이여야 합니다.", "error")
        return redirect(url_for("product_detail", product_id=product_id))

    review = Review(product_id=product_id, user_id=current_user.id, rating=rating, content=content)
    db.session.add(review)
    db.session.commit()
    flash("리뷰가 등록되었습니다.", "success")
    return redirect(url_for("product_detail", product_id=product_id))

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

    available_coupons = []
    if current_user.is_authenticated:
        now = datetime.utcnow()
        available_coupons = (
            UserCoupon.query.join(Coupon)
            .filter(
                UserCoupon.user_id == current_user.id,
                UserCoupon.used == False,
                Coupon.active == True,
                Coupon.valid_from <= now,
                Coupon.valid_to >= now
            )
            .all()
        )

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

        total_amount = sum(((ci.product.base_price or 0) + ((ci.variant.price or 0) if ci.variant else 0)) * ci.quantity
                           for ci in cart_items)

        # ✅ 쿠폰 적용
        discount_amount = 0
        applied_user_coupon_id = None
        user_coupon_id = request.form.get("user_coupon_id", type=int)
        if current_user.is_authenticated and user_coupon_id:
            uc = (UserCoupon.query.join(Coupon)
                  .filter(UserCoupon.id == user_coupon_id,
                          UserCoupon.user_id == current_user.id,
                          UserCoupon.used == False,
                          Coupon.active == True,
                          Coupon.valid_from <= datetime.utcnow(),
                          Coupon.valid_to >= datetime.utcnow())
                  .first())
            if uc and total_amount >= (uc.coupon.min_amount or 0):
                if uc.coupon.discount_type == "percent":
                    discount_amount = total_amount * uc.coupon.discount_value // 100
                else:
                    discount_amount = uc.coupon.discount_value
                discount_amount = min(discount_amount, total_amount)
                applied_user_coupon_id = uc.id  # ✅ 주문에 어떤 쿠폰을 적용했는지 저장
                

        final_amount = max(0, total_amount - discount_amount)

        if payment_method == "무통장입금":
            status = "입금대기"
        else:
            status = "결제대기"

        # 주문 생성
        new_order = Order(
            user_id=current_user.id if current_user.is_authenticated else None,
            guest_email=guest_email if not current_user.is_authenticated else None,
            name=name,
            phone=phone,
            base_address=base_address,
            detail_address=detail_address,
            payment_method=payment_method,
            status=status,  
            created_at=datetime.now(KST),
            applied_user_coupon_id=applied_user_coupon_id,
            discount_amount=discount_amount
        )
        db.session.add(new_order)
        db.session.flush()  # new_order.id 확보

        # 주문 아이템 생성 + 장바구니 제거
        for item in cart_items:
            # 정가
            original_price = (item.product.base_price or 0) + ((item.variant.price or 0) if item.variant else 0)
            # 할인 단가 (쿠폰 적용 시)
            discount_price = original_price
            discount_reason = None

            if discount_amount > 0 and applied_user_coupon_id:
                # 쿠폰이 전체 주문에 적용되면 비율 계산
                coupon = Coupon.query.join(UserCoupon).filter(UserCoupon.id == applied_user_coupon_id).first()
                discount_reason = coupon.name if coupon else "쿠폰할인"

                # 각 상품에 균등 분배 (비율 계산)
                total_price_sum = sum(((ci.product.base_price or 0) + ((ci.variant.price or 0) if ci.variant else 0)) * ci.quantity for ci in cart_items)
                share_ratio = (original_price * item.quantity) / total_price_sum
                per_item_discount = int(discount_amount * share_ratio / item.quantity)
                discount_price = max(0, original_price - per_item_discount)

            db.session.add(OrderItem(
                order_id=new_order.id,
                variant_id=item.variant_id,
                quantity=item.quantity,
                original_price=original_price,
                discount_price=discount_price,
                discount_reason=discount_reason
            ))

        db.session.commit()

        # ✅ 결제 페이지로 이동
        if payment_method == "무통장입금":
            # 무통장입금은 결제창 띄우지 않고 바로 주문완료 페이지로 이동
            new_order.status = "입금대기"  # 상태를 명확히 설정
            if applied_user_coupon_id:
                uc = UserCoupon.query.get(applied_user_coupon_id)
                if uc and not uc.used:
                    uc.used = True
                    uc.used_at = datetime.utcnow()
                    db.session.add(uc)

            # ✅ 모든 order_items의 할인 금액/사유가 null이면 다시 계산 반영
            for oi in new_order.items:
                if oi.discount_price is None:
                    oi.discount_price = oi.original_price
                if discount_amount > 0 and applied_user_coupon_id:
                    if not oi.discount_reason:
                        coupon = Coupon.query.join(UserCoupon).filter(UserCoupon.id == applied_user_coupon_id).first()
                        oi.discount_reason = coupon.name if coupon else "쿠폰할인"

            if current_user.is_authenticated:
                CartItem.query.filter_by(user_id=current_user.id).delete()
            else:
                sid = session.get("session_id")
                if sid:
                    CartItem.query.filter_by(session_id=sid).delete()

            db.session.commit()
            return redirect(url_for("order_complete", order_id=new_order.id))
        else:
            # 카드, 카카오, 네이버 등은 결제창으로 이동
            return redirect(url_for("payment", order_id=new_order.id))

    # GET: 장바구니 화면
    cart_items = base_q.all()
    total = sum(((ci.product.base_price or 0) + ((ci.variant.price or 0) if ci.variant else 0)) * ci.quantity
                for ci in cart_items)

    user_info = {}
    if current_user.is_authenticated:
        user_info = {
            "name": current_user.name,
            "phone": current_user.phone,
            "base_address": current_user.base_address,
            "detail_address": current_user.detail_address,
            "email": current_user.email,
        }

    return render_template("checkout.html",
                           cart_items=cart_items,
                           total=total,
                           user_info=user_info,
                           user_id=user_id,
                           available_coupons=available_coupons)

@app.route("/payment/<int:order_id>")
def payment(order_id):
    order = Order.query.get_or_404(order_id)
    items_total = sum(int(oi.original_price or 0) * int(oi.quantity or 0) for oi in order.items)
    amount = max(0, items_total - int(order.discount_amount or 0))  # ✅ 할인 반영

    user_info = User.query.get(order.user_id) if order.user_id else None
    return render_template(
        "payment.html",
        order=order,
        amount=amount,   # ✅ 할인 반영된 금액 전달
        user_info=user_info,
        imp_code=app.config["IMP_CODE"]
    )

# 모바일 결제시 아래 코드가 없으면 404 오류가 남 팝업 방식이 아닌 모바일 방식으로 나오기 때문에
@app.route("/payment-complete/<int:order_id>")
def payment_complete(order_id):
    imp_uid = request.args.get("imp_uid")
    merchant_uid = request.args.get("merchant_uid")
    print("📦 [모바일 콜백] imp_uid:", imp_uid, "merchant_uid:", merchant_uid)

    try:
        if not imp_uid:
            # 🔹 imp_uid가 없을 경우: DB에 사전등록된 merchant_uid로 Payment 검색
            pay = Payment.query.filter_by(order_id=order_id).order_by(Payment.id.desc()).first()
            if pay:
                merchant_uid = pay.merchant_uid
                print("✅ DB에서 merchant_uid 복구:", merchant_uid)

        if not merchant_uid:
            print("❌ merchant_uid 누락, 복구 불가")
            return redirect(url_for("checkout"))

        # 🔹 아임포트에서 imp_uid 조회 (merchant_uid 기반)
        if not imp_uid:
            token = _get_iamport_token()
            res = requests.get(
                f"https://api.iamport.kr/payments/find/{merchant_uid}",
                headers={"Authorization": token},
                timeout=7
            )
            if res.status_code == 200:
                data = res.json().get("response")
                if data and data.get("imp_uid"):
                    imp_uid = data["imp_uid"]
                    print("✅ imp_uid 복구 성공:", imp_uid)
        
        # imp_uid 확보 후 검증 요청
        if imp_uid:
            verify_res = requests.post(
                f"{request.url_root}pay/verify",
                json={"imp_uid": imp_uid, "merchant_uid": merchant_uid, "order_id": order_id},
                headers={"Content-Type": "application/json"},
                timeout=7
            )
            v = verify_res.json()
            if v.get("ok"):
                print("✅ 검증 성공:", v)
                return redirect(url_for("order_complete", order_id=order_id))
            else:
                print("❌ 검증 실패:", v)
    except Exception as e:
        print("❌ 모바일 검증 예외:", e)

    print("⚠️ imp_uid 또는 검증 실패, checkout으로 이동")
    return redirect(url_for("checkout"))

@app.route("/pay/prepare", methods=["POST"])
def pay_prepare():
    data = request.get_json()
    order_id = data.get("order_id")
    order = Order.query.get(order_id)
    if not order:
        return jsonify({"ok": False, "msg": "주문을 찾을 수 없습니다."}), 404

    # ✅ Access Token 발급
    imp_key = app.config['IMP_KEY']
    imp_secret = app.config['IMP_SECRET']
    token_res = requests.post(
        "https://api.iamport.kr/users/getToken",
        data={"imp_key": imp_key, "imp_secret": imp_secret}
    ).json()

    if token_res['code'] != 0:
        return jsonify({"ok": False, "msg": "토큰 발급 실패"}), 400

    access_token = token_res['response']['access_token']

    # ✅ merchant_uid 생성
    merchant_uid = f"order_{order.id}_{int(datetime.utcnow().timestamp())}"

    # ✅ 사전 등록 (금액 검증용)
    res = requests.post(
        "https://api.iamport.kr/payments/prepare",
        headers={"Authorization": access_token},
        data={"merchant_uid": merchant_uid, "amount": order.total_price}
    ).json()

    if res['code'] != 0:
        return jsonify({"ok": False, "msg": res.get('message', '사전등록 실패')}), 400

    return jsonify({
        "ok": True,
        "imp_code": app.config['IMP_CODE'],
        "merchant_uid": merchant_uid,
        "amount": order.total_price
    })

@app.route("/pay/verify", methods=["POST"])
def pay_verify():
    data = request.get_json(silent=True) or {}
    imp_uid = data.get("imp_uid")
    merchant_uid = data.get("merchant_uid")
    order_id = data.get("order_id")

    token = _get_iamport_token()
    imp_res = requests.get(
        f"https://api.iamport.kr/payments/{imp_uid}",
        headers={"Authorization": token},
        timeout=7
    )
    if imp_res.status_code != 200:
        return jsonify(ok=False, message="결제사 검증 실패"), 400

    imp_data = imp_res.json().get("response", {})
    status = imp_data.get("status")
    amount = imp_data.get("amount")
    pg_provider = imp_data.get("pg_provider")
    pay_method = imp_data.get("pay_method")
    fail_reason = imp_data.get("fail_reason", "")

    pay = Payment.query.filter_by(merchant_uid=merchant_uid).first()
    order = Order.query.get(order_id)
    if not pay:
        pay = Payment(order_id=order_id, merchant_uid=merchant_uid, amount=amount)
        db.session.add(pay)

    # ✅ 반드시 imp_uid 저장 (덮어쓰기 포함)
    if not pay.imp_uid or pay.imp_uid != imp_uid:
        pay.imp_uid = imp_uid

    pay.pg_provider = pg_provider
    pay.method = pay_method
    pay.amount = amount

    if not order:
        db.session.rollback()
        return jsonify(ok=False, message="주문 정보를 찾을 수 없습니다."), 400

    if status == "paid":
        # ✅ 결제 성공
        pay.status = "paid"
        pay.paid_at = datetime.utcnow()
        order.status = "paid"

        # ✅ 쿠폰은 결제 성공시에만 사용 처리
        if getattr(order, "applied_user_coupon_id", None):
            uc = UserCoupon.query.filter_by(
                id=order.applied_user_coupon_id,
                user_id=order.user_id
            ).first()
            if uc and not uc.used:
                uc.used = True
                db.session.add(uc)

        # ✅ 장바구니도 성공시에만 비움
        if order.user_id:
            CartItem.query.filter_by(user_id=order.user_id).delete()
        elif order.guest_email:
            sid = session.get("session_id")
            if sid:
                CartItem.query.filter_by(session_id=sid).delete()

    elif status in ("ready", "vbank_issued"):
        # 가상계좌 발급 등 → 입금 대기
        pay.status = "ready"
        order.status = "pending"

    else:
        # ❌ 실패, 취소, 응답 없음 등
        pay.status = "failed"
        order.status = "failed"
        pay.fail_reason = fail_reason or "결제 실패 또는 취소됨"

        print(f"❌ [결제실패] 주문 {order.id}, 사유: {pay.fail_reason}")

    db.session.commit()
    return jsonify(ok=True, status=pay.status)

@app.route("/pay/fail", methods=["POST"])
def pay_fail():
    data = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    reason = data.get("error", "결제 실패 또는 취소")

    order = Order.query.get(order_id)
    if order:
        order.status = "failed"
        db.session.commit()
        print(f"❌ 결제 실패 처리됨: 주문 {order_id}, 사유: {reason}")

    return jsonify(ok=True)

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
    pending_orders = Order.query.filter(
        Order.status.in_(["pending", "ready", "입금대기", "결제대기"])
    ).count()
    # 답변 대기중 문의 개수
    new_inquiries_count = Inquiry.query.filter_by(status="답변 대기").count()
    return render_template("admin/dashboard.html",
        pending_orders=pending_orders,
        new_inquiries_count=new_inquiries_count)

@app.route("/admin/coupons")
@login_required
def admin_coupons():
    if not current_user.is_admin:
        flash("관리자만 접근 가능합니다.", "error")
        return redirect(url_for("home"))

    coupons = Coupon.query.order_by(Coupon.id.desc()).all()
    return render_template("admin/coupons.html", coupons=coupons)

@app.route("/admin/coupons/add", methods=["GET", "POST"])
@login_required
def admin_add_coupon():
    if not current_user.is_admin:
        flash("관리자만 접근 가능합니다.", "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        discount_type = request.form.get("discount_type")
        discount_value = request.form.get("discount_value", type=int)
        min_amount = request.form.get("min_amount", type=int)
        valid_from = datetime.strptime(request.form.get("valid_from"), "%Y-%m-%d")
        valid_to = datetime.strptime(request.form.get("valid_to"), "%Y-%m-%d")

        coupon = Coupon(
            name=name,
            description=description,
            discount_type=discount_type,
            discount_value=discount_value,
            min_amount=min_amount,
            valid_from=valid_from,
            valid_to=valid_to,
            active=True
        )
        db.session.add(coupon)
        db.session.commit()
        flash("쿠폰이 생성되었습니다.", "success")
        return redirect(url_for("admin_coupons"))
    return render_template("admin/add_coupon.html")

@app.route("/admin/coupons/<int:coupon_id>/delete", methods=["POST"])
@login_required
def admin_delete_coupon(coupon_id):
    if not current_user.is_admin:
        return redirect(url_for("home"))
    coupon = Coupon.query.get_or_404(coupon_id)
    db.session.delete(coupon)
    db.session.commit()
    flash("쿠폰이 삭제되었습니다.", "success")
    return redirect(url_for("admin_coupons"))

@app.route("/admin/coupons/<int:coupon_id>/assign", methods=["POST"])
@login_required
def admin_assign_coupon(coupon_id):
    if not current_user.is_admin:
        flash("관리자만 접근 가능합니다.", "error")
        return redirect(url_for("home"))

    email = (request.form.get("email") or "").strip()
    if not email:
        flash("이메일을 입력하세요.", "error")
        return redirect(url_for("admin_coupons"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("해당 이메일을 가진 사용자가 존재하지 않습니다.", "error")
        return redirect(url_for("admin_coupons"))

    coupon = Coupon.query.get(coupon_id)
    if not coupon:
        flash("쿠폰을 찾을 수 없습니다.", "error")
        return redirect(url_for("admin_coupons"))

    # 이미 지급 여부 확인 (중복 방지)
    existing = UserCoupon.query.filter_by(user_id=user.id, coupon_id=coupon.id).first()
    if existing:
        flash("이미 이 쿠폰을 지급받은 사용자입니다.", "error")
        return redirect(url_for("admin_coupons"))

    uc = UserCoupon(user_id=user.id, coupon_id=coupon.id, used=False)
    db.session.add(uc)
    db.session.commit()

    flash(f"{user.email} 님에게 쿠폰 '{coupon.name}' 지급 완료!", "success")
    return redirect(url_for("admin_coupons"))

@app.route("/admin/returns", methods=["GET", "POST"])
@login_required
def admin_returns():
    if not current_user.is_admin:
        flash("관리자만 접근 가능합니다.", "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        return_id = request.form.get("return_id", type=int)
        action = request.form.get("action")

        req = OrderReturn.query.get(return_id)
        if not req:
            flash("해당 주문의 반품/교환 요청을 찾을 수 없습니다.", "error")
            return redirect(url_for("admin_returns"))

        order = Order.query.get(req.order_id)

        if action == "approve":
            req.status = "승인완료"
            if order:
                order.status = "반품처리중" if req.type == "return" else "교환처리중"
            flash(f"주문 {req.order_id}의 요청이 승인되었습니다.", "success")

        elif action == "reject":
            req.status = "거절됨"
            if order:
                order.status = "배송완료"
            flash(f"주문 {req.order_id}의 요청이 거절되었습니다.", "info")

        elif action == "complete":
            req.status = "처리완료"
            if order:
                if req.type == "return":
                    order.status = "반품완료"
                else:
                    order.status = "교환완료"
            flash(f"주문 {req.order_id}의 { '반품' if req.type == 'return' else '교환' }이 완료되었습니다.", "success")

        db.session.commit()
        return redirect(url_for("admin_returns"))

    # GET
    return_orders = (
        OrderReturn.query
        .options(joinedload(OrderReturn.user))
        .order_by(OrderReturn.created_at.desc())
        .all()
    )
    return render_template("admin/admin_returns.html", return_orders=return_orders)

@app.route("/admin/products")
@login_required
def admin_products():
    if not current_user.is_admin:
        flash("관리자만 접근 가능합니다.", "error")
        return redirect(url_for("home"))
    # ✅ 관리자 페이지는 전체 상품 (숨김 포함)
    products = Product.query.order_by(Product.id.desc()).all()
    return render_template("admin/products.html", products=products)

@app.route("/admin/products/add", methods=["GET", "POST"])
@login_required
def admin_add_product():
    if not current_user.is_admin:
        flash("관리자만 접근할 수 있습니다.", "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form.get("name")
        base_price = request.form.get("base_price", type=int)
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
        if image_file:
            new_product.image_data = image_file.read()
            new_product.image_mime = image_file.mimetype  # 예: image/png

        # ✅ 팜플렛 업로드
        pamphlet = request.files.get("pamphlet")
        if pamphlet:
            new_product.pamphlet_data = pamphlet.read()
            new_product.pamphlet_mime = pamphlet.mimetype
            new_product.pamphlet_name = pamphlet.filename

        db.session.add(new_product)
        db.session.commit()

        flash("상품이 추가되었습니다.", "success")
        return redirect(url_for("admin_product_options", product_id=new_product.id))

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

        price = int(request.form.get("price", 0))
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
        product.base_price = request.form.get("base_price", type=int)
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

    try:
        product.is_active = False  # ✅ 숨김 처리
        db.session.commit()
        flash("상품이 비활성화(숨김 처리)되었습니다.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"상품 비활성화 중 오류 발생: {str(e)}", "error")

    return redirect(url_for("admin_products"))

@app.route("/admin/products/<int:product_id>/toggle", methods=["POST"])
@login_required
def admin_toggle_product(product_id):
    if not current_user.is_admin:
        flash("관리자만 접근할 수 있습니다.", "error")
        return redirect(url_for("home"))

    product = Product.query.get_or_404(product_id)
    product.is_active = not product.is_active   # ✅ 토글
    db.session.commit()
    flash(f"상품 '{product.name}' 상태가 {'활성' if product.is_active else '숨김'}으로 변경되었습니다.", "success")
    return redirect(url_for("admin_products"))

from flask import send_file
from io import BytesIO

@app.route("/image/<int:product_id>")
def serve_product_image(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.image_data:
        abort(404)
    return send_file(
        BytesIO(product.image_data),
        mimetype=product.image_mime
    )
from flask import Response, stream_with_context
from urllib.parse import quote

@app.route("/video/<int:video_id>")
def serve_video(video_id):
    video = Video.query.get_or_404(video_id)
    if not video.video_data:
        abort(404)

    # ✅ 한글 제목 안전 처리 (UTF-8 → RFC5987 표준 방식)
    safe_filename = "video.mp4"
    if video.title:
        safe_filename = f"{video.title}.mp4" if not video.title.lower().endswith(".mp4") else video.title
    safe_filename_encoded = quote(safe_filename)  # URL-safe 인코딩

    def generate():
        chunk_size = 1024 * 1024  # 1MB씩 전송
        data = video.video_data
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]

    response = Response(
        stream_with_context(generate()),
        mimetype=video.video_mime or "video/mp4",
    )

    # ✅ 표준 UTF-8 헤더로 지정 (latin-1 깨짐 방지)
    response.headers["Content-Disposition"] = f"inline; filename*=UTF-8''{safe_filename_encoded}"
    response.headers["Accept-Ranges"] = "bytes"
    return response

@app.route("/pamphlet/<int:product_id>")
def serve_pamphlet(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.pamphlet_data:
        abort(404)
    return send_file(
        BytesIO(product.pamphlet_data),
        mimetype=product.pamphlet_mime,
        as_attachment=True,
        download_name=product.pamphlet_name
    )

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
        title = request.form.get("title")
        description = request.form.get("description")
        tags = request.form.get("tags")
        file = request.files.get("video")

        if not file or not title:
            flash("제목과 영상을 입력해주세요.", "error")
            return redirect(url_for("admin_add_video"))
        
        mime = file.mimetype
        data = file.read()

        video = Video(
            title=title,
            description=description,
            tags=tags,
            video_data=data,
            video_mime=mime
        )
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
    if not current_user.is_admin:
        abort(403)

    video = Video.query.get_or_404(video_id)

    # ✅ 파일 경로 접근 불필요 (DB에만 저장하므로)
    db.session.delete(video)
    db.session.commit()

    flash("영상이 성공적으로 삭제되었습니다.", "success")
    return redirect(url_for("admin_videos"))

@app.route("/admin/ads", methods=["GET", "POST"])
@login_required
def admin_ads():
    if not current_user.is_admin:
        abort(403)

    if request.method == "POST":
        title = request.form.get("title")
        subtitle = request.form.get("subtitle")
        description = request.form.get("description")
        link_url = request.form.get("link_url")

        new_ad = Advertisement(
            title=title,
            subtitle=subtitle,
            description=description,
            link_url=link_url,
            is_active=True
        )
        db.session.add(new_ad)
        db.session.flush()  # ad.id 확보

        files = request.files.getlist("images")
        for f in files:
            if f and f.filename:
                img = AdvertisementImage(
                    ad_id=new_ad.id,
                    image_data=f.read(),
                    image_mime=f.mimetype
                )
                db.session.add(img)

        db.session.commit()
        flash("광고가 등록되었습니다.", "success")
        return redirect(url_for("admin_ads"))

    ads = Advertisement.query.order_by(Advertisement.order).all()
    return render_template("admin/admin_ads.html", ads=ads)

@app.route("/admin/ad_image/<int:image_id>")
@login_required
def admin_ad_image(image_id):
    if not current_user.is_admin:
        abort(403)
    image = AdvertisementImage.query.get_or_404(image_id)
    return Response(image.image_data, mimetype=image.image_mime)

@app.route("/admin/ads/<int:ad_id>/toggle", methods=["POST"])
@login_required
def toggle_ad(ad_id):
    if not current_user.is_admin:
        abort(403)
    ad = Advertisement.query.get_or_404(ad_id)
    ad.is_active = not ad.is_active
    db.session.commit()
    return redirect(url_for("admin_ads"))

@app.route("/admin/ads/<int:ad_id>/delete", methods=["POST"])
@login_required
def delete_ad(ad_id):
    if not current_user.is_admin:
        abort(403)
    ad = Advertisement.query.get_or_404(ad_id)
    db.session.delete(ad)
    db.session.commit()
    flash("광고가 삭제되었습니다.", "info")
    return redirect(url_for("admin_ads"))

@app.route("/admin/ads/<int:ad_id>/move", methods=["POST"])
@login_required
def move_ad(ad_id):
    if not current_user.is_admin:
        abort(403)
    direction = request.form.get("direction")
    ad = Advertisement.query.get_or_404(ad_id)

    if direction == "up":
        prev_ad = Advertisement.query.filter(Advertisement.order < ad.order).order_by(Advertisement.order.desc()).first()
        if prev_ad:
            ad.order, prev_ad.order = prev_ad.order, ad.order
    elif direction == "down":
        next_ad = Advertisement.query.filter(Advertisement.order > ad.order).order_by(Advertisement.order.asc()).first()
        if next_ad:
            ad.order, next_ad.order = next_ad.order, ad.order

    db.session.commit()
    return redirect(url_for("admin_ads"))

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

    # -----------------
    # 상태 변경 (POST)
    # -----------------
    if request.method == "POST":
        order_id = request.form.get("order_id", type=int)
        new_status = request.form.get("status")
        if new_status == "cancelled":  # 철자 혼용 보정
            new_status = "canceled"

        order = Order.query.get(order_id)
        if order:
            if not order.is_read:
                order.is_read = True   # 읽음 처리
            if new_status:
                order.status = new_status
            db.session.commit()
            flash(f"주문 {order.id} 상태가 '{new_status}'로 변경되었습니다.", "success")
        return redirect(url_for("admin_orders"))

    # -----------------
    # 필터 (GET)
    # -----------------
    q = (request.args.get("q") or "").strip()
    period = request.args.get("period") or "1m"            # '1m' | '3m' | '6m' | '5y'
    start_date_str = request.args.get("start_date")  # 'YYYY-MM'
    end_date_str   = request.args.get("end_date")    # 'YYYY-MM'

    start_dt, end_dt = _compute_date_range(period, start_date_str, end_date_str)

    # 기본 쿼리 + 기간
    query = (
        Order.query
        .filter(Order.created_at >= start_dt, Order.created_at < end_dt)
    )

    # 검색(주문자명, 회원이메일, 비회원이메일, 주문번호, 상품명)
    if q:
        query = (
            query
            .outerjoin(User, Order.user_id == User.id)
            .outerjoin(OrderItem, OrderItem.order_id == Order.id)
            .outerjoin(ProductVariant, ProductVariant.id == OrderItem.variant_id)
            .outerjoin(Product, Product.id == ProductVariant.product_id)
            .filter(
                or_(
                    User.name.ilike(f"%{q}%"),
                    User.email.ilike(f"%{q}%"),
                    Order.guest_email.ilike(f"%{q}%"),
                    cast(Order.id, String).ilike(f"%{q}%"),
                    Product.name.ilike(f"%{q}%"),
                )
            )
        )

    # 정렬 + N+1 방지 로딩
    orders = (
        query
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

    # 이번에 조회된 주문들을 '읽음'으로 처리 (알림 뱃지 감소)
    any_unread = False
    for o in orders:
        if not o.is_read:
            o.is_read = True
            any_unread = True
    if any_unread:
        db.session.commit()

    # 템플릿에서 쓰기 쉬운 요약 필드 구성
    for o in orders:
        names = []
        for it in o.items:
            product = it.variant.product if (it.variant and it.variant.product) else None
            names.append(product.name if product else "(삭제된 상품)")
        summary = names[0] + (f" 외 {len(names)-1}개" if len(names) > 1 else "") if names else "-"

        qty_sum      = sum((it.quantity or 0) for it in o.items)
        items_total  = sum(int(it.original_price or 0) * int(it.quantity or 0) for it in o.items)
        final_amount = max(0, items_total - int(o.discount_amount or 0))

        who    = (o.user.name if o.user else (o.name or "비회원"))
        email  = (o.user.email if o.user else (o.guest_email or "-"))
        phone  = o.phone or (o.user.phone if (o.user and getattr(o.user, "phone", None)) else "-")
        address = " ".join([x for x in [o.base_address, o.detail_address] if x]) or "-"

        pay_status = o.payment.status if o.payment else "-"

        # 동적 속성(템플릿에서 o._xxx로 접근)
        o._summary       = summary
        o._qty_sum       = int(qty_sum)
        o._items_total   = int(items_total)
        o._discount      = int(o.discount_amount or 0)
        o._final_amount  = int(final_amount)
        o._who           = who
        o._email         = email
        o._phone         = phone
        o._address       = address
        o._pay_status    = pay_status

        # 쿠폰명(표시용)
        o._coupon_name = None
        if o.applied_user_coupon_id:
            uc = UserCoupon.query.options(joinedload(UserCoupon.coupon)).get(o.applied_user_coupon_id)
            if uc and uc.coupon:
                o._coupon_name = uc.coupon.name

        # 철자 혼용 보정
        if getattr(o, "status", None) == "cancelled":
            o.status = "canceled"

    return render_template(
        "admin/admin_orders.html",
        orders=orders,
        status_options=STATUS_OPTIONS,
        timedelta=timedelta,
        # ▶ 템플릿 필터 상태 기억용
        selected_period=period,
        start_date=start_date_str,
        end_date=end_date_str,
        search_query=q,
    )

@app.route("/admin/order_items/<int:order_id>")
@login_required
def admin_order_items(order_id):
    # ✅ 관계를 variant → product까지 타고 들어감
    order = (
        Order.query
        .options(joinedload(Order.items)
                 .joinedload(OrderItem.variant)
                 .joinedload(ProductVariant.product))
        .get(order_id)
    )

    if not order:
        return jsonify({"error": "Order not found"}), 404

    items = []
    for item in order.items:
        product_name = item.variant.product.name if item.variant and item.variant.product else "상품정보 없음"
        variant_info = ", ".join([f"{k}: {v}" for k, v in (item.variant.options or {}).items()]) if item.variant else ""
        items.append({
            "name": product_name,
            "variant": variant_info,
            "qty": item.quantity,
            "price": item.discount_price or item.original_price or 0,
        })

    return jsonify({"items": items})

@app.route("/admin/orders/confirm_deposit/<int:order_id>", methods=["POST"])
@login_required
def admin_confirm_deposit(order_id):
    if not current_user.is_admin:
        abort(403)

    order = Order.query.get_or_404(order_id)

    # 무통장입금 주문만 처리
    if order.payment_method != "무통장입금":
        flash("무통장입금 주문만 입금 확인 가능합니다.", "error")
        return redirect(url_for("admin_orders"))
    
    items_total = sum(int(i.original_price or 0) * int(i.quantity or 0) for i in order.items)
    final_amount = max(0, items_total - int(order.discount_amount or 0))

    # ✅ 상태 변경 (주문 + 결제)
    order.status = "결제완료"
    order.updated_at = datetime.now(KST)  # 한국시간 기준으로 갱신

    payment = Payment.query.filter_by(order_id=order.id).first()

    if not payment:
        payment = Payment(
            order_id=order.id,
            merchant_uid=f"DEPOSIT_{order.id}_{int(datetime.utcnow().timestamp())}",
            imp_uid=f"MANUAL_{order.id}",   # ✅ 수동 결제라도 imp_uid 형태로 만들어둠
            amount=final_amount,
            status="paid",
            paid_at=datetime.utcnow(),
            method="vbank",
            pg_provider="manual"  # 표기용
        )
        db.session.add(payment)
    else:
        payment.status = "paid"
        payment.paid_at = datetime.utcnow()
        payment.amount = final_amount

    # 쿠폰 사용 처리
    if getattr(order, "applied_user_coupon_id", None):
        uc = UserCoupon.query.filter_by(id=order.applied_user_coupon_id, user_id=order.user_id).first()
        if uc and not uc.used:
            uc.used = True
            db.session.add(uc)

    db.session.commit()

    # ✅ 이메일 발송 (비회원 / 회원 구분)
    recipient = order.guest_email or (order.user.email if order.user else None)
    if recipient:
        try:
            msg = Message(
                subject=_("[UGAMALL] 입금이 확인되었습니다."),
                sender=("UGAMALL", app.config['MAIL_USERNAME']),
                recipients=[recipient]
            )
            msg.html = f"""
            <div style="font-family:'Noto Sans KR',sans-serif; max-width:480px; margin:auto; border:1px solid #e5e7eb; border-radius:8px; overflow:hidden; background:#ffffff;">
              <div style="text-align:center; padding:32px 20px 16px;">
                <img src="https://ugamall.co.kr/static/images/Uga_logo.png" alt="UGAMALL" style="height:38px; margin-bottom:20px;">
              </div>

              <hr style="border:none; border-top:1px solid #e5e7eb; margin:0;">

              <div style="padding:32px 28px 24px; text-align:center;">
                <h2 style="font-size:20px; font-weight:700; color:#111827; margin-bottom:12px;">{_('입금 확인 안내')}</h2>

                <p style="font-size:15px; color:#374151; line-height:1.6; margin-bottom:20px;">
                {_('안녕하세요,')} <strong>{order.name}</strong> {_('고객님.')}<br>
                {_('주문번호')} <strong>#{order.id}</strong> {_('의 입금이 확인되어 결제가 완료되었습니다.')}<br>
                {_('곧 배송 준비를 시작하겠습니다.')}.
                </p>

                <div style="display:inline-block; background:#111827; color:#ffffff; font-weight:700; letter-spacing:1px; font-size:18px; padding:12px 32px; border-radius:6px; margin:20px 0;">
                {_('결제 금액:')} {final_amount:,.0f}{_('원')}
                </div>

                <p style="font-size:13px; color:#9ca3af; margin-top:24px; line-height:1.6;">
                {_('주문 상세 정보는 마이페이지 또는 주문조회에서 확인하실 수 있습니다.')}<br>
                <a href="https://ugamall.co.kr/guest_orders" target="_blank" style="color:#2563eb; text-decoration:none;">{_('주문 내역 바로가기')}</a>
                </p>
              </div>

              <hr style="border:none; border-top:1px solid #e5e7eb; margin:0;">

              <div style="text-align:center; background:#f9fafb; padding:16px; font-size:12px; color:#9ca3af;">
                © 2025 UGAMALL. All rights reserved.
              </div>
            </div>
            """

            mail.send(msg)
        except Exception as e:
            print("⚠️ 이메일 발송 실패:", e)

    flash(f"주문번호 {order.id}의 입금이 확인되어 결제완료로 변경되었습니다.", "success")
    return redirect(url_for("admin_orders"))

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
    # ✅ 관리자 권한 체크
    if not current_user.is_admin:
        flash("관리자만 접근 가능합니다.", "error")
        return redirect(url_for("home"))

    # ✅ 답변 등록 처리
    if request.method == "POST":
        inquiry_id = request.form.get("inquiry_id")
        answer = request.form.get("answer")

        inquiry = Inquiry.query.get(inquiry_id)
        if inquiry:
            if not inquiry.is_read:
                inquiry.is_read = True
            inquiry.answer = answer
            inquiry.status = "답변 완료"
            inquiry.answered_at = datetime.now(KST)
            db.session.commit()
            flash("답변이 등록되었습니다.", "success")
        return redirect(url_for("admin_inquiries"))

    # ✅ 검색 및 기간 필터
    q = request.args.get("q", "").strip()
    period = request.args.get("period", "1m") # ✅ 기본값 1개월
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    inquiries = Inquiry.query

    # 🔍 검색 필터
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        inquiries = (
            inquiries.outerjoin(User)
            .filter(
                or_(
                    Inquiry.title.ilike(like),
                    Inquiry.content.ilike(like),
                    Inquiry.guest_email.ilike(like),
                    User.name.ilike(like),
                    User.email.ilike(like),
                )
            )
        )

    # 📅 기간 필터
    now = datetime.now(KST)

    if period == "1m":
        inquiries = inquiries.filter(Inquiry.created_at >= now - timedelta(days=30))
    elif period == "3m":
        inquiries = inquiries.filter(Inquiry.created_at >= now - timedelta(days=90))
    elif period == "6m":
        inquiries = inquiries.filter(Inquiry.created_at >= now - timedelta(days=180))
    elif period == "5y":
        pass  # 전체 보기

    # 📆 직접 입력한 기간 필터
    if start_date:
        try:
            start_dt = datetime.strptime(start_date + "-01", "%Y-%m-%d")
            inquiries = inquiries.filter(Inquiry.created_at >= start_dt)
        except Exception:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date + "-28", "%Y-%m-%d")
            inquiries = inquiries.filter(Inquiry.created_at <= end_dt)
        except Exception:
            pass

    # ✅ 정렬 및 조회
    inquiries = inquiries.order_by(Inquiry.created_at.desc()).all()

    # ✅ 읽음 처리
    for iq in inquiries:
        if not iq.is_read:
            iq.is_read = True
    db.session.commit()

    # ✅ 렌더링
    return render_template(
        "admin_inquiries.html",
        inquiries=inquiries,
        selected_period=period,
        start_date=start_date,
        end_date=end_date,
        search_query=q,
    )


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
    sort = request.args.get("sort", "new")

    query = Product.query.filter(Product.is_active == True)   # 🔽 조건 추가

    if q:
        query = query.filter(Product.name.contains(q))
    if category:
        query = query.filter(Product.category==category)

    query = query.filter(Product.base_price>=price_min, Product.base_price<=price_max)

    if sort == "low":
        query = query.order_by(Product.base_price.asc())
    elif sort == "high":
        query = query.order_by(Product.base_price.desc())
    elif sort == "name":
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.id.desc())

    products = query.all()
    
    videos = []
    if video:
        if q:
            videos = Video.query.filter(Video.title.contains(q)).all()
        else:
            videos = Video.query.all()

    categories = [c[0] for c in db.session.query(Product.category).distinct()]
    return render_template("search.html", products=products, videos=videos, categories=categories, video_filter=True,q=q,selected_sort=sort)

# ----------------------------
# ✅ 쿠폰 받기 (사용자용)
# ----------------------------
@app.route("/available_coupons")
@login_required
def available_coupons():
    """아직 받지 않은 쿠폰 목록 조회"""
    now = datetime.utcnow()
    # 이미 받은 쿠폰 ID 추출
    received_ids = [uc.coupon_id for uc in UserCoupon.query.filter_by(user_id=current_user.id).all()]

    # 아직 안 받은 활성 쿠폰 목록
    coupons = Coupon.query.filter(
        Coupon.active == True,
        Coupon.valid_from <= now,
        Coupon.valid_to >= now,
        ~Coupon.id.in_(received_ids)
    ).all()

    data = [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description or "",
            "discount_type": c.discount_type,
            "discount_value": c.discount_value,
            "min_amount": c.min_amount,
            "valid_to": c.valid_to.strftime("%Y-%m-%d")
        }
        for c in coupons
    ]
    return jsonify(data)


@app.route("/claim_coupons", methods=["POST"])
@login_required
def claim_coupons():
    """선택한 쿠폰 수령"""
    ids = request.json.get("coupon_ids", [])
    if not ids:
        return jsonify({"ok": False, "msg": "선택된 쿠폰이 없습니다."}), 400

    added = 0
    for cid in ids:
        coupon = Coupon.query.get(cid)
        if not coupon or not coupon.active:
            continue

        # 이미 받은 쿠폰은 건너뜀
        existing = UserCoupon.query.filter_by(user_id=current_user.id, coupon_id=cid).first()
        if existing:
            continue

        uc = UserCoupon(user_id=current_user.id, coupon_id=cid, used=False)
        db.session.add(uc)
        added += 1

    db.session.commit()
    return jsonify({"ok": True, "added": added})

@app.route('/send_email_code', methods=['POST'])
def send_email_code():
    email = request.form.get('email')
    if not email:
        return jsonify({'message': '이메일을 입력해주세요.'})

    code = ''.join(random.choices(string.digits, k=6))
    session['email_code'] = code
    session["email_code_time"] = time.time()
    session["email_target"] = email

    try:
        msg = Message(_("[UGAMALL] 이메일 인증 코드"), recipients=[email])
        msg.html = f"""
        <div style="font-family:'Noto Sans KR',sans-serif; max-width:480px; margin:auto; border:1px solid #e5e7eb; border-radius:8px; overflow:hidden; background:#ffffff;">
          <div style="text-align:center; padding:32px 20px 16px;">
            <img src="https://ugamall.co.kr/static/images/Uga_logo.png" alt="UGAMALL" style="height:38px; margin-bottom:20px;">
          </div>

          <hr style="border:none; border-top:1px solid #e5e7eb; margin:0;">

          <div style="padding:32px 28px 24px; text-align:center;">
            <h2 style="font-size:20px; font-weight:700; color:#111827; margin-bottom:12px;">{_('이메일 인증 요청')}</h2>

            <p style="font-size:15px; color:#374151; line-height:1.6; margin-bottom:20px;">
              {_('안녕하세요,')} <strong>{_('유가몰')}</strong> {_('입니다.')}<br>
                {_('이메일 인증을 완료하시려면 아래 인증코드를 입력해주세요.')}<br>
                <strong>{_('인증코드는 5분간만 유효합니다.')}</strong>
            </p>

            <div style="display:inline-block; background:#111827; color:#ffffff; font-weight:700; letter-spacing:2px; font-size:24px; padding:14px 40px; border-radius:6px; margin:20px 0;">
              {code}
            </div>

            <p style="font-size:13px; color:#9ca3af; margin-top:24px; line-height:1.6;">
            {_('본 메일은 발신 전용이며 회신되지 않습니다.')}<br>
            <strong>{_('유가몰')}</strong> {_('은 고객님의 계정을 안전하게 보호하기 위해 최선을 다하고 있습니다.')}.
            </p>
          </div>

          <hr style="border:none; border-top:1px solid #e5e7eb; margin:0;">

          <div style="text-align:center; background:#f9fafb; padding:16px; font-size:12px; color:#9ca3af;">
            © 2025 UGAMALL. All rights reserved.
          </div>
        </div>
        """

        mail.send(msg)
        return jsonify({"message": f"인증 메일이 {email} 로 전송되었습니다."})
    except Exception as e:
        print("⚠️ 메일 전송 실패:", e)
        return jsonify({"message": "메일 전송 중 오류가 발생했습니다."}), 500

@app.route("/verify_email_code", methods=["POST"])
def verify_email_code():
    code = request.form.get("code")
    saved_code = session.get("email_code")
    saved_time = session.get("email_code_time")
    email_target = session.get("email_target")

    # 세션 만료 또는 코드 없음
    if not saved_code or not saved_time:
        return jsonify({"message": "인증 코드가 만료되었거나 존재하지 않습니다."}), 400

    # 5분(300초) 제한
    if time.time() - saved_time > 300:
        session.pop("email_code", None)
        session.pop("email_code_time", None)
        session.pop("email_target", None)
        return jsonify({"message": "인증 코드가 만료되었습니다. 다시 시도해주세요."}), 400

    # 코드 일치 확인
    if code == saved_code:
        session["email_verified"] = True
        session["verified_email"] = email_target  # ✅ 인증된 이메일 저장
        print("✅ 세션 상태 (인증 후):", dict(session))
        return jsonify({"message": f"{email_target} 인증이 완료되었습니다!"})
    else:
        return jsonify({"message": "인증코드가 올바르지 않습니다."}), 400

@app.route('/autocomplete')
def autocomplete():
    q = request.args.get("q","")
    results = []
    if q:
        # 🔽 숨김 상품은 제외
        results = [p.name for p in Product.query.filter(Product.name.contains(q), Product.is_active == True).all()]
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

@app.route("/verify_password", methods=["POST"])
@login_required
def verify_password():
    data = request.get_json()
    if not data or "password" not in data:
        return jsonify({"success": False}), 400

    # ✅ 여기 수정 (password → password_hash)
    if hasattr(current_user, "password_hash") and check_password_hash(current_user.password_hash, data["password"]):
        return jsonify({"success": True})
    else:
        return jsonify({"success": False})

with app.app_context():
    db.create_all()
    print("✅ DB schema created (or already exists)")

if __name__=="__main__":
    port = int(os.environ.get("PORT", 5000))  # Render가 주입한 PORT 사용
    app.run(host="0.0.0.0", port=port)
