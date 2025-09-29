# create_admin.py
from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    admin = User(
        email="admin@ugamall.com",
        password=generate_password_hash("1234"),
        is_admin=True,
        name="관리자"
    )
    db.session.add(admin)
    db.session.commit()
    print("✅ 관리자 계정이 생성되었습니다!")
